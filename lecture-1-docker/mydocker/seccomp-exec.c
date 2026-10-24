// usage: seccomp-exec <profile> <cmd> [args...]
// profile: по одному имени syscall в строке, # — комментарий. Перечисленные вызовы → EPERM.
#include <errno.h>
#include <seccomp.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <profile> <cmd> [args...]\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("profile"); return 2; }

    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);   // по умолчанию разрешено (denylist)
    char line[128];
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, " \t\r\n#")] = 0;
        if (!*line) continue;
        int nr = seccomp_syscall_resolve_name(line);
        if (nr == __NR_SCMP_ERROR) { fprintf(stderr, "unknown syscall: %s\n", line); continue; }
        if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), nr, 0) < 0) {
            fprintf(stderr, "rule failed: %s\n", line);
            return 2;
        }
    }
    fclose(f);
    // libseccomp сам выставляет no_new_privs: без него непривилегированный процесс фильтр загрузить не может
    if (seccomp_load(ctx) < 0) { perror("seccomp_load"); return 2; }
    seccomp_release(ctx);
    execvp(argv[2], argv + 2);
    perror("execvp");
    return 127;
}
