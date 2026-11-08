/* English patch loader for Taiko Risshiden V DX (dinput8.dll proxy).
 *
 * The game imports dinput8.dll, so Windows loads this file from the game folder. It
 * forwards DirectInput8Create to the system dinput8.dll and applies the English
 * program patch (tl_patch.bin, written by tools/loader.py) to the game in memory:
 * the game's .exe file on disk is never changed.
 *
 * When: the program code may still be encrypted while DLLs load (Steam's wrapper
 * decrypts it at startup), so the patch is applied from the first call the game's own
 * startup code makes to a hooked import (GetSystemTimeAsFileTime / QueryPerformance-
 * Counter, called by the C runtime right after the entry point), once the CRC32 of
 * every original byte range matches. DirectInput8Create tries once more; if the patch
 * still cannot be applied the game runs unchanged (Japanese) and tl_patch.log says why.
 *
 * Where: the English code and text block (.tl) belongs right above the image (tl_rva);
 * if something else is mapped there (Wine may put a DLL right after the image) it goes
 * to the nearest free 64 KB slot and every reference to it is adjusted (fixup list).
 *
 * Built with clang + lld-link, no C runtime and no Windows SDK (tools/loader.py).
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef long long i64;
typedef void *HANDLE;
typedef int BOOL;
typedef long HRESULT;
#define WINAPI __stdcall
#define IMPORT __declspec(dllimport)

IMPORT void *WINAPI GetModuleHandleW(const u16 *);
IMPORT u32 WINAPI GetModuleFileNameW(void *, u16 *, u32);
IMPORT u32 WINAPI GetSystemDirectoryW(u16 *, u32);
IMPORT void *WINAPI LoadLibraryW(const u16 *);
IMPORT void *WINAPI GetProcAddress(void *, const char *);
IMPORT HANDLE WINAPI CreateFileW(const u16 *, u32, u32, void *, u32, u32, HANDLE);
IMPORT BOOL WINAPI ReadFile(HANDLE, void *, u32, u32 *, void *);
IMPORT BOOL WINAPI WriteFile(HANDLE, const void *, u32, u32 *, void *);
IMPORT u32 WINAPI SetFilePointer(HANDLE, i64, void *, u32);
IMPORT u32 WINAPI GetFileSize(HANDLE, u32 *);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT void *WINAPI VirtualAlloc(void *, u64, u32, u32);
IMPORT BOOL WINAPI VirtualFree(void *, u64, u32);
IMPORT BOOL WINAPI VirtualProtect(void *, u64, u32, u32 *);
IMPORT BOOL WINAPI FlushInstructionCache(HANDLE, const void *, u64);
IMPORT HANDLE WINAPI GetCurrentProcess(void);
IMPORT void WINAPI GetSystemTimeAsFileTime(void *);
IMPORT BOOL WINAPI QueryPerformanceCounter(void *);
IMPORT void *WINAPI GetProcessHeap(void);
IMPORT void *WINAPI HeapAlloc(void *, u32, u64);

#define GENERIC_READ 0x80000000u
#define GENERIC_WRITE 0x40000000u
#define FILE_SHARE_READ 1
#define OPEN_EXISTING 3
#define OPEN_ALWAYS 4
#define INVALID_HANDLE ((HANDLE)(i64)-1)
#define MEM_COMMIT 0x1000
#define MEM_RESERVE 0x2000
#define MEM_RELEASE 0x8000
#define PAGE_READWRITE 0x04
#define PAGE_EXECUTE_READ 0x20
#define PAGE_EXECUTE_READWRITE 0x40
#define PREFERRED_BASE 0x140000000ull

/* clang may turn loops into calls to these */
void *memcpy(void *d, const void *s, u64 n) { u8 *a = d; const u8 *b = s; while (n--) *a++ = *b++; return d; }
void *memset(void *d, int c, u64 n) { u8 *a = d; while (n--) *a++ = (u8)c; return d; }

/* ---------------------------------------------------------------- small helpers */
static u16 dir[520];                       /* game folder, with trailing backslash */
static u32 dirlen;

static void wcat(u16 *d, const u16 *a, const char *b) {
    while (*a) *d++ = *a++;
    while (*b) *d++ = (u8)*b++;
    *d = 0;
}

static HANDLE logf = INVALID_HANDLE;
static void log_s(const char *s) {
    u32 n = 0, w;
    if (logf == INVALID_HANDLE) {
        u16 p[600];
        wcat(p, dir, "tl_patch.log");
        logf = CreateFileW(p, GENERIC_WRITE, FILE_SHARE_READ, 0, OPEN_ALWAYS, 0x80, 0);
        if (logf == INVALID_HANDLE) return;
        SetFilePointer(logf, 0, 0, 2);
    }
    while (s[n]) n++;
    WriteFile(logf, s, n, &w, 0);
}
static void log_x(const char *label, u64 v) {
    char b[40]; int i = 0, k;
    log_s(label);
    b[i++] = '0'; b[i++] = 'x';
    for (k = 60; k >= 0; k -= 4) { int d = (v >> k) & 15; if (i > 2 || d || k == 0) b[i++] = "0123456789abcdef"[d]; }
    b[i++] = '\r'; b[i++] = '\n'; b[i] = 0;
    log_s(b);
}

static u32 crc_table[256];
static void crc_init(void) {
    for (u32 i = 0; i < 256; i++) {
        u32 c = i;
        for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        crc_table[i] = c;
    }
}

/* ---------------------------------------------------------------- the patch file */
/* tl_patch.bin, little endian:
 *   "TLP2", u32 size of the image it fits, u32 n_hooks, u32 hook IAT rva [n_hooks],
 *   u32 tl_rva, u32 tl_size, u32 n_ranges,
 *   n_ranges x { u32 rva, u32 len, u32 crc32 of the original bytes (before relocation),
 *                u32 n_rel, u16 rel offsets [n_rel] (qwords the base relocation adjusts),
 *                padding to 4, u8 new bytes [len], padding to 4 },
 *   u8 tl [tl_size], padding to 4,
 *   u32 n_fix, u32 fix [n_fix]: rva | kind << 30 (rva >= tl_rva: inside tl), kind 0 =
 *     int32 += d, 1 = int32 -= d, 2 = qword += d, d = where tl went - (base + tl_rva) */
static u8 *blob;
static u32 blob_size;
static u8 *base;
static i64 delta;
static int done, failed;
static void *real_gstaft, *real_qpc;
static u32 hook_rva[4], n_hooks;

static u32 rd32(const u8 *p) { return p[0] | p[1] << 8 | p[2] << 16 | (u32)p[3] << 24; }

static int load_blob(void) {
    u16 p[600];
    u32 got;
    wcat(p, dir, "tl_patch.bin");
    HANDLE f = CreateFileW(p, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0x80, 0);
    if (f == INVALID_HANDLE) { log_s("tl_patch.bin not found next to the game\r\n"); return 0; }
    blob_size = GetFileSize(f, 0);
    blob = HeapAlloc(GetProcessHeap(), 0, blob_size);
    if (!blob || !ReadFile(f, blob, blob_size, &got, 0) || got != blob_size) { CloseHandle(f); return 0; }
    CloseHandle(f);
    if (blob_size < 32 || rd32(blob) != 0x32504C54) { log_s("tl_patch.bin: bad header\r\n"); return 0; }
    if (rd32(blob + 4) != 0) {
        /* image size check: the patch fits one build of the program */
        u8 *nt = base + rd32(base + 0x3C);
        if (rd32(nt + 0x50) != rd32(blob + 4)) { log_x("program image size differs: ", rd32(nt + 0x50)); return 0; }
    }
    return 1;
}

/* walk the ranges: mode 0 = check the originals, 1 = check already patched,
 * 2 = write the patch, 3 = only find the tl bytes (*tl_out) */
static int ranges(int mode, const u8 **tl_out) {
    const u8 *q = blob + 12 + 4 * rd32(blob + 8);
    u32 n = rd32(q + 8);
    q += 12;
    for (u32 r = 0; r < n; r++) {
        u32 rva = rd32(q), len = rd32(q + 4), crc = rd32(q + 8), nrel = rd32(q + 12);
        const u8 *rel = q + 16;                 /* u32 offsets, ascending */
        const u8 *nb = rel + 4 * nrel;
        u8 *m = base + rva;
        if (mode == 0) {
            u32 c = 0xFFFFFFFFu, k = 0;
            for (u32 i = 0; i < len; i++) {
                u8 b = m[i];
                while (k < nrel && rd32(rel + 4 * k) + 8 <= i) k++;
                if (k < nrel && rd32(rel + 4 * k) <= i) {
                    u32 o = rd32(rel + 4 * k);
                    u64 v; memcpy(&v, m + o, 8); v -= (u64)delta;
                    b = (u8)(v >> (8 * (i - o)));
                }
                c = crc_table[(c ^ b) & 255] ^ (c >> 8);
            }
            if ((c ^ 0xFFFFFFFFu) != crc) return 0;
        } else if (mode == 1) {
            u32 k = 0;
            for (u32 i = 0; i < len; i++) {
                while (k < nrel && rd32(rel + 4 * k) + 8 <= i) k++;
                if (k < nrel && rd32(rel + 4 * k) <= i) continue;
                if (m[i] != nb[i]) return 0;
            }
        } else if (mode == 2) {
            u32 old;
            VirtualProtect(m, len, PAGE_EXECUTE_READWRITE, &old);
            memcpy(m, nb, len);
            for (u32 k = 0; k < nrel; k++) {
                u32 o = rd32(rel + 4 * k);
                u64 v; memcpy(&v, m + o, 8); v += (u64)delta; memcpy(m + o, &v, 8);
            }
            VirtualProtect(m, len, old, &old);
            FlushInstructionCache(GetCurrentProcess(), m, len);
        }
        q = nb + ((len + 3) & ~3u);
    }
    if (tl_out) *tl_out = q;
    return 1;
}

static void unhook(void);

/* the blob's byte for image rva (inside a range), or 0 */
static u8 *range_byte(u32 rva) {
    const u8 *q = blob + 12 + 4 * rd32(blob + 8);
    u32 n = rd32(q + 8);
    q += 12;
    for (u32 r = 0; r < n; r++) {
        u32 a = rd32(q), len = rd32(q + 4), nrel = rd32(q + 12);
        const u8 *nb = q + 16 + 4 * nrel;
        if (rva >= a && rva < a + len) return (u8 *)nb + (rva - a);
        q = nb + ((len + 3) & ~3u);
    }
    return 0;
}

/* .tl goes d bytes away from base + tl_rva: adjust every reference to it in the blob */
static void fix_refs(i64 d, u32 tl_rva, u32 tl_size, u8 *tl) {
    const u8 *f = tl + ((tl_size + 3) & ~3u);
    u32 n = rd32(f);
    f += 4;
    for (u32 i = 0; i < n; i++) {
        u32 v = rd32(f + 4 * i), rva = v & 0x3FFFFFFF, kind = v >> 30;
        u8 *p = rva >= tl_rva ? tl + (rva - tl_rva) : range_byte(rva);
        if (!p) continue;
        if (kind == 2) { u64 x; memcpy(&x, p, 8); x += (u64)d; memcpy(p, &x, 8); }
        else { u32 x; memcpy(&x, p, 4); x += (u32)(kind ? -d : d); memcpy(p, &x, 4); }
    }
}

/* returns 1 when the patch is in place (now or before) */
static volatile long busy;
static int try_patch_locked(const char *when);
static int try_patch(const char *when) {
    if (done) return 1;
    if (failed || !blob) return 0;
    if (__atomic_exchange_n(&busy, 1, __ATOMIC_ACQUIRE)) return done;   /* another thread */
    int r = try_patch_locked(when);
    __atomic_store_n(&busy, 0, __ATOMIC_RELEASE);
    return r;
}
static int try_patch_locked(const char *when) {
    if (done) return 1;
    if (!ranges(0, 0)) {
        if (ranges(1, 0)) { log_s("program already patched\r\n"); done = 1; unhook(); return 1; }
        return 0;                       /* still encrypted, or another version */
    }
    const u8 *q = blob + 12 + 4 * rd32(blob + 8);
    u32 tl_rva = rd32(q), tl_size = rd32(q + 4);
    const u8 *tl;
    ranges(3, &tl);                     /* mode 3: just find the tl bytes */
    u8 *want = base + tl_rva, *t = 0;
    u64 sz = (tl_size + 0xFFFF) & ~0xFFFFull;
#ifdef TEST_MOVE
    /* test: something already sits at tl_rva (1: one slot, 2: every free slot above) */
    for (i64 k = 0; k < (TEST_MOVE == 1 ? 1 : 0x4000); k++) VirtualAlloc(want + k * 0x10000, 0x10000, MEM_RESERVE, 1);
#endif
    /* at tl_rva, else the nearest free slot above, else below the image (all within
     * 1 GB, so every rel32 still reaches) */
    for (i64 k = 0; k < 0x4000 && !t; k++) {
        u8 *c = want + k * 0x10000;
        t = VirtualAlloc(c, sz, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        if (t && t != c) { VirtualFree(t, 0, MEM_RELEASE); t = 0; }
    }
    for (i64 k = 1; k < 0x4000 && !t; k++) {
        u8 *c = (u8 *)(((u64)base & ~0xFFFFull) - sz - (u64)(k - 1) * 0x10000);
        t = VirtualAlloc(c, sz, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        if (t && t != c) { VirtualFree(t, 0, MEM_RELEASE); t = 0; }
    }
    if (!t) {
        log_x("could not reserve the patch block near ", (u64)want);
        failed = 1;
        return 0;
    }
    if (t != want) {
        log_x("patch block moved to ", (u64)t);
        fix_refs((i64)(t - want), tl_rva, tl_size, (u8 *)tl);
    }
    memcpy(t, tl, tl_size);
    u32 old;
    VirtualProtect(t, tl_size, PAGE_EXECUTE_READ, &old);
    FlushInstructionCache(GetCurrentProcess(), t, tl_size);
    ranges(2, 0);
    done = 1;
    unhook();
    log_s("English patch applied (");
    log_s(when);
    log_s(")\r\n");
    return 1;
}

/* ---------------------------------------------------------------- import hooks */
static void set_iat(u32 rva, void *fn) {
    void **slot = (void **)(base + rva);
    u32 old;
    VirtualProtect(slot, 8, PAGE_READWRITE, &old);
    *slot = fn;
    VirtualProtect(slot, 8, old, &old);
}

static void WINAPI hook_gstaft(void *ft) {
    try_patch("at startup");
    ((void (WINAPI *)(void *))real_gstaft)(ft);
}
static BOOL WINAPI hook_qpc(void *c) {
    try_patch("at startup");
    return ((BOOL (WINAPI *)(void *))real_qpc)(c);
}

static void hook(void) {
    for (u32 i = 0; i < n_hooks; i++) {
        void **slot = (void **)(base + hook_rva[i]);
        if (real_gstaft && *slot == real_gstaft) set_iat(hook_rva[i], (void *)hook_gstaft);
        else if (real_qpc && *slot == real_qpc) set_iat(hook_rva[i], (void *)hook_qpc);
    }
}
static void unhook(void) {
    for (u32 i = 0; i < n_hooks; i++) {
        void **slot = (void **)(base + hook_rva[i]);
        if (*slot == (void *)hook_gstaft) set_iat(hook_rva[i], real_gstaft);
        else if (*slot == (void *)hook_qpc) set_iat(hook_rva[i], real_qpc);
    }
}

/* ---------------------------------------------------------------- dinput8 proxy */
typedef HRESULT (WINAPI *di8create_t)(void *, u32, const void *, void **, void *);
static di8create_t real_create;

__declspec(dllexport) HRESULT WINAPI DirectInput8Create(void *inst, u32 ver, const void *riid, void **out, void *outer) {
    if (!done && !failed) {
        try_patch("late, at DirectInput8Create");
        if (!done) {
            failed = 1;
            log_s("English patch NOT applied: this game version is not supported\r\n");
            void *u = LoadLibraryW(u"user32.dll");
            int (WINAPI *mb)(void *, const u16 *, const u16 *, u32) = u ? GetProcAddress(u, "MessageBoxW") : 0;
            if (mb) mb(0, u"The English patch could not be applied: this version of the game is "
                          u"not supported. The game will run in Japanese. See tl_patch.log.",
                       u"Taiko Risshiden V DX English", 0x30);
        }
    }
    if (!real_create) {
        u16 p[600];
        u32 n = GetSystemDirectoryW(p, 520);
        wcat(p + n, u"", "\\dinput8.dll");
        void *m = LoadLibraryW(p);
        real_create = m ? (di8create_t)GetProcAddress(m, "DirectInput8Create") : 0;
        if (!real_create) return (HRESULT)0x80004005;
    }
    return real_create(inst, ver, riid, out, outer);
}

BOOL WINAPI DllMain(void *self, u32 reason, void *reserved) {
    (void)self; (void)reserved;
    if (reason != 1) return 1;
    base = GetModuleHandleW(0);
    delta = (i64)((u64)base - PREFERRED_BASE);
    dirlen = GetModuleFileNameW(0, dir, 512);
    while (dirlen && dir[dirlen - 1] != '\\' && dir[dirlen - 1] != '/') dirlen--;
    dir[dirlen] = 0;
    crc_init();
    log_s("---\r\n");
    log_x("game base ", (u64)base);
    if (!load_blob()) { failed = 1; return 1; }
    n_hooks = rd32(blob + 8);
    if (n_hooks > 4) n_hooks = 4;
    for (u32 i = 0; i < n_hooks; i++) hook_rva[i] = rd32(blob + 12 + 4 * i);
    /* the import slots must hold the real functions (kernel32 or kernelbase): only
     * then are they hooked */
    void *k32 = GetModuleHandleW(u"kernel32.dll"), *kb = GetModuleHandleW(u"kernelbase.dll");
    const char *names[2] = {"GetSystemTimeAsFileTime", "QueryPerformanceCounter"};
    void **real[2] = {&real_gstaft, &real_qpc};
    for (u32 i = 0; i < n_hooks && i < 2; i++) {
        void *cur = *(void **)(base + hook_rva[i]);
        if (cur && (cur == GetProcAddress(k32, names[i]) || (kb && cur == GetProcAddress(kb, names[i]))))
            *real[i] = cur;
        else
            log_s("import slot not resolved: no startup hook\r\n");
    }
#ifdef TEST_DEFER
    hook();                             /* test: as if the code were still encrypted */
#else
    if (!try_patch("while loading")) hook();
#endif
    return 1;
}
