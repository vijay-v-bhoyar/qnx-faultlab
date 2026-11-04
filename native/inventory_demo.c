/*
 * FaultLab application drill: lost reply after a committed inventory reservation.
 * Only the service child forked here is controlled. Journal directory must be new.
 * Process-crash demonstration, not power-loss or distributed exactly-once proof.
 */
#define _QNX_SOURCE 1
#include <sys/neutrino.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAGIC UINT32_C(0x494e5632)
#define MAX_ENTRIES 16
#define TIMEOUT_MS 1000
struct request { uint32_t magic, operation_id, quantity; };
struct reply { uint32_t magic; int remaining, applied, duplicate; };
struct entry { unsigned id, quantity; };
struct observation {
    uint64_t started, ended;
    int rc, error, payload_ok;
    struct reply reply;
};
static pid_t child = -1;
static int connection = -1;
static volatile sig_atomic_t cancelled;
static unsigned sequence;
static const char *implementation;
static char journal[4096];

static void signal_stop(int signo) { cancelled = signo; }
static uint64_t now_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == -1) { perror("clock_gettime"); exit(2); }
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}
static void sleep_briefly(void) {
    struct timespec delay = {0, 10000000};
    (void)nanosleep(&delay, NULL);
}
static int reap(int terminate, int *exit_code) {
    unsigned i;
    int status;
    pid_t found;
    if (child <= 0) return 0;
    if (terminate && kill(child, SIGTERM) == -1 && errno != ESRCH) return -1;
    for (i = 0; i < 200; ++i) {
        found = waitpid(child, &status, WNOHANG);
        if (found == child) {
            child = -1;
            if (exit_code) *exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : 255;
            return 0;
        }
        if (found == -1 && errno != EINTR) return -1;
        if (i == 100 && kill(child, SIGKILL) == -1 && errno != ESRCH) return -1;
        sleep_briefly();
    }
    errno = ETIMEDOUT;
    return -1;
}
static void cleanup(void) {
    if (connection >= 0) { (void)ConnectDetach(connection); connection = -1; }
    (void)reap(1, NULL);
}
static void check_cancel(void) { if (cancelled) exit(128 + cancelled); }
static void die(const char *what) { perror(what); exit(2); }

/* The log is retained, and never rewritten. A killed VM/disk is out of scope. */
static int load_log(struct entry *entries, int *count, int *stock) {
    unsigned id, quantity;
    int scanned;
    FILE *file = fopen(journal, "r");
    if (!file) return -1;
    *count = 0; *stock = 10;
    while ((scanned = fscanf(file, "%u %u", &id, &quantity)) == 2) {
        if (*count >= MAX_ENTRIES || !id || !quantity || quantity > (unsigned)*stock) {
            fclose(file); errno = EINVAL; return -1;
        }
        entries[*count].id = id; entries[*count].quantity = quantity;
        ++*count; *stock -= (int)quantity;
    }
    if (scanned != EOF || ferror(file)) { fclose(file); errno = EINVAL; return -1; }
    return fclose(file);
}
static int append_log(unsigned id, unsigned quantity) {
    char line[80];
    size_t offset = 0;
    int length = snprintf(line, sizeof(line), "%u %u\n", id, quantity);
    int fd = open(journal, O_WRONLY | O_APPEND);
    if (fd == -1) return -1;
    while (offset < (size_t)length) {
        ssize_t written = write(fd, line + offset, (size_t)length - offset);
        if (written == -1 && errno == EINTR) continue;
        if (written <= 0) { close(fd); return -1; }
        offset += (size_t)written;
    }
    if (fsync(fd) == -1) { int saved = errno; close(fd); errno = saved; return -1; }
    return close(fd);
}
static void service(int ready, int crash_after_commit) {
    struct entry entries[MAX_ENTRIES];
    struct sigaction action;
    struct request request;
    struct reply reply;
    struct _msg_info info;
    int channel, receive_id, count, stock, i, duplicate;
    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_DFL; sigemptyset(&action.sa_mask);
    (void)sigaction(SIGINT, &action, NULL); (void)sigaction(SIGTERM, &action, NULL);
    (void)sigaction(SIGPIPE, &action, NULL);
    if (load_log(entries, &count, &stock) == -1) _exit(70);
    channel = ChannelCreate(0);
    if (channel == -1 || write(ready, &channel, sizeof(channel)) != (ssize_t)sizeof(channel)) _exit(71);
    close(ready);
    for (;;) {
        memset(&request, 0, sizeof(request));
        receive_id = MsgReceive(channel, &request, sizeof(request), &info);
        if (receive_id <= 0) _exit(72);
        if (info.msglen != (int)sizeof(request) || request.magic != MAGIC ||
            !((request.operation_id == 0 && request.quantity == 0) ||
              (request.operation_id == 101 && request.quantity == 3) ||
              (request.operation_id == 102 && request.quantity == 2))) {
            (void)MsgError(receive_id, EINVAL); continue;
        }
        duplicate = 0;
        if (request.operation_id) {
            for (i = 0; i < count; ++i) {
                if (entries[i].id == request.operation_id) {
                    if (entries[i].quantity != request.quantity) _exit(73);
                    duplicate = 1;
                }
            }
            if (!duplicate || strcmp(implementation, "naive") == 0) {
                if (count >= MAX_ENTRIES || stock < (int)request.quantity) {
                    (void)MsgError(receive_id, ENOSPC); continue;
                }
                if (append_log(request.operation_id, request.quantity) == -1) _exit(74);
                entries[count].id = request.operation_id;
                entries[count].quantity = request.quantity;
                ++count; stock -= (int)request.quantity;
                duplicate = 0;
            }
            /* Actual process termination AFTER fsync/close, BEFORE MsgReply. */
            if (crash_after_commit) _exit(42);
        }
        reply.magic = MAGIC; reply.remaining = stock;
        reply.applied = count; reply.duplicate = duplicate;
        if (MsgReply(receive_id, 0, &reply, sizeof(reply)) == -1) _exit(75);
    }
}
static void start_service(int crash_after_commit) {
    int ready[2], channel, status;
    ssize_t count;
    struct pollfd waiter;
    check_cancel();
    if (child > 0 || connection >= 0) { errno = EBUSY; die("service ownership"); }
    if (pipe(ready) == -1) die("pipe");
    child = fork();
    if (child == 0) { close(ready[0]); service(ready[1], crash_after_commit); _exit(76); }
    close(ready[1]);
    if (child == -1) { close(ready[0]); die("fork"); }
    waiter.fd = ready[0]; waiter.events = POLLIN; waiter.revents = 0;
    status = poll(&waiter, 1, TIMEOUT_MS + 1000);
    if (status <= 0 || !(waiter.revents & POLLIN)) {
        close(ready[0]); check_cancel(); errno = ETIMEDOUT; die("service ready");
    }
    count = read(ready[0], &channel, sizeof(channel)); close(ready[0]);
    if (count != (ssize_t)sizeof(channel)) { errno = EIO; die("service ready data"); }
    check_cancel();
    connection = ConnectAttach(0, child, channel, _NTO_SIDE_CHANNEL, 0);
    if (connection == -1) die("ConnectAttach");
}
static struct observation send_request(unsigned operation, unsigned quantity) {
    struct request request = {MAGIC, operation, quantity};
    struct observation o;
    struct sigevent notify;
    uint64_t timeout = UINT64_C(1000000) * TIMEOUT_MS;
    memset(&o, 0, sizeof(o));
    o.reply.remaining = -1; o.reply.applied = -1;
    check_cancel();
    SIGEV_UNBLOCK_INIT(&notify);
    o.started = now_ns();
    if (TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_SEND | _NTO_TIMEOUT_REPLY,
                     &notify, &timeout, NULL) == -1) die("TimerTimeout");
    o.rc = MsgSend(connection, &request, sizeof(request), &o.reply, sizeof(o.reply));
    o.error = o.rc == -1 ? errno : 0; o.ended = now_ns();
    o.payload_ok = o.rc == 0 && o.reply.magic == MAGIC &&
        o.reply.remaining >= 0 && o.reply.remaining <= 10 &&
        o.reply.applied >= 0 && o.reply.applied <= MAX_ENTRIES &&
        (o.reply.duplicate == 0 || o.reply.duplicate == 1);
    check_cancel();
    return o;
}
static void emit(const char *phase, const char *outcome, const char *detail,
                 const struct observation *o, unsigned operation, unsigned quantity,
                 int exit_code) {
    const char *error = "";
    check_cancel();
    if (o && o->error) error = o->error == ESRCH ? "ESRCH" :
        o->error == ETIMEDOUT ? "ETIMEDOUT" : o->error == EBADF ? "EBADF" : "OTHER";
    printf("{\"type\":\"event\",\"seq\":%u,\"scenario\":\"inventory_retry\","
           "\"phase\":\"%s\",\"monotonic_ns\":%" PRIu64 ",\"outcome\":\"%s\","
           "\"errno_name\":\"%s\",\"detail\":\"%s\"",
           ++sequence, phase, o ? o->ended : now_ns(), outcome, error, detail);
    if (o) printf(",\"started_ns\":%" PRIu64 ",\"duration_ns\":%" PRIu64
                  ",\"payload_ok\":%s,\"operation_id\":%u,\"quantity\":%u,"
                  "\"remaining\":%d,\"applied\":%d,\"duplicate\":%s",
                  o->started, o->ended - o->started, o->payload_ok ? "true" : "false",
                  operation, quantity, o->reply.remaining, o->reply.applied,
                  o->reply.duplicate ? "true" : "false");
    if (exit_code >= 0) printf(",\"exit_code\":%d", exit_code);
    printf("}\n");
    if (fflush(stdout) == EOF || ferror(stdout)) die("capture output");
    check_cancel();
}
static void reply_event(const char *phase, struct observation *o, unsigned op, unsigned qty, const char *detail) {
    *o = send_request(op, qty);
    emit(phase, o->rc == 0 ? "reply" : "error", detail, o, op, qty, -1);
}
int main(int argc, char **argv) {
    struct sigaction action;
    struct utsname target;
    struct observation lost, recovered, retry, followup, final;
    const char *state_dir = NULL;
    int fd, exit_code = -1, i, matches;
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("faultlab-inventory 0.2.0"); return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("faultlab_inventory --implementation naive|idempotent --state-dir NEW_DIRECTORY");
        puts("Only its own disposable service; retains journal; process-crash demo, not power-loss proof.");
        return 0;
    }
    for (i = 1; i < argc; i += 2) {
        if (i + 1 >= argc) return 2;
        if (strcmp(argv[i], "--implementation") == 0 && !implementation) implementation = argv[i+1];
        else if (strcmp(argv[i], "--state-dir") == 0 && !state_dir) state_dir = argv[i+1];
        else return 2;
    }
    if (!implementation || !state_dir ||
        (strcmp(implementation, "naive") && strcmp(implementation, "idempotent"))) return 2;
    if (uname(&target) == -1 || strcmp(target.sysname, "QNX") || strncmp(target.release, "8.", 2)) {
        fputs("QNX8 target required\n", stderr); return 2;
    }
    if (snprintf(journal, sizeof(journal), "%s/journal.txt", state_dir) >= (int)sizeof(journal)) return 2;
    if (mkdir(state_dir, 0700) == -1) { perror("new state directory"); return 2; }
    fd = open(journal, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd == -1) { perror("new journal"); return 2; }
    if (close(fd) == -1) return 2;
    memset(&action, 0, sizeof(action));
    action.sa_handler = signal_stop; sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) == -1 || sigaction(SIGTERM, &action, NULL) == -1) return 2;
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &action, NULL) == -1 || atexit(cleanup)) return 2;
    setvbuf(stdout, NULL, _IOLBF, 0);
    printf("{\"type\":\"session\",\"schema_version\":2,\"tool_version\":\"0.2.0\","
           "\"session_id\":\"inventory-%ld-%" PRIu64 "\",\"source_kind\":\"qnx-native\","
           "\"sysname\":\"QNX\",\"release\":\"%s\",\"machine\":\"%s\","
           "\"timeout_ms\":%d,\"clock\":\"CLOCK_MONOTONIC\","
           "\"contract\":\"inventory-retry/1\",\"implementation\":\"%s\"}\n",
           (long)getpid(), now_ns(), target.release, target.machine, TIMEOUT_MS, implementation);
    emit("begin", "started", "Initial stock10; reserve101=3, retry101=3, reserve102=2; isolated owned service", NULL, 0, 0, -1);
    start_service(1);
    lost = send_request(101, 3);
    emit("request", lost.rc == -1 && lost.error == ESRCH ? "server_gone" : "error",
         "Reply lost after journal synchronization; producer observes client result", &lost, 101, 3, -1);
    if (ConnectDetach(connection) == -1) die("ConnectDetach");
    connection = -1;
    if (reap(0, &exit_code) == -1) die("crashed child reap");
    emit("crash_exit", "exited", "Observed original service exit status", NULL, 0, 0, exit_code);
    start_service(0);
    reply_event("recovered_state", &recovered, 0, 0, "Restart replays retained journal BEFORE retry");
    reply_event("recovery_request", &retry, 101, 3, "Same operation101 retried; stock must remain7/applied1");
    reply_event("followup_request", &followup, 102, 2, "Distinct operation102 must make stock5/applied2");
    reply_event("final_state", &final, 0, 0, "Independent read of final application state");
    matches = lost.rc == -1 && lost.error == ESRCH && exit_code == 42 &&
        recovered.payload_ok && recovered.reply.remaining == 7 && recovered.reply.applied == 1 && !recovered.reply.duplicate &&
        retry.payload_ok && retry.reply.remaining == 7 && retry.reply.applied == 1 && retry.reply.duplicate &&
        followup.payload_ok && followup.reply.remaining == 5 && followup.reply.applied == 2 && !followup.reply.duplicate &&
        final.payload_ok && final.reply.remaining == 5 && final.reply.applied == 2 && !final.reply.duplicate;
    if (ConnectDetach(connection) == -1) die("ConnectDetach");
    connection = -1;
    if (reap(1, NULL) == -1) die("restarted child cleanup");
    emit("cleanup", "clean", "Owned service reaped; journal retained in new state directory", NULL, 0, 0, -1);
    emit("end", "complete", "Host independently checks stock and operation invariants", NULL, 0, 0, -1);
    check_cancel();
    return matches ? 0 : 1;
}
