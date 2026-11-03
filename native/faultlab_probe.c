/*
 * FaultLab isolated QNX 8.0 message-passing drills.
 * Only children forked by this process are signalled. No arbitrary target API.
 * Native compilation/execution must be verified with a licensed QNX SDK/target.
 */
#define _QNX_SOURCE 1
#include <sys/neutrino.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <errno.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define TOOL_VERSION "0.1.0"
#define TOKEN UINT32_C(0x46544c42)
#define REPLY_TOKEN (TOKEN ^ UINT32_C(0x00ff00ff))

static volatile sig_atomic_t stop_signal;
static pid_t owned_pid = -1;
static unsigned sequence;
static unsigned timeout_ms = 250;

struct observation {
    uint64_t started;
    uint64_t ended;
    int rc;
    int error;
    int payload_ok;
};

static void request_stop(int signo) { stop_signal = signo; }

static uint64_t now_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == -1) {
        perror("faultlab: clock_gettime");
        exit(2);
    }
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static void brief_sleep(void) {
    struct timespec delay = {0, 10000000};
    (void)nanosleep(&delay, NULL);
}

/* A PID is forgotten immediately when reaped; no PID-name lookup or process scan. */
static int reap_owned(void) {
    int status;
    pid_t result;
    unsigned attempt;
    if (owned_pid <= 0) return 0;
    do { result = waitpid(owned_pid, &status, WNOHANG); } while (result == -1 && errno == EINTR);
    if (result == owned_pid || (result == -1 && errno == ECHILD)) {
        owned_pid = -1;
        return 0;
    }
    if (result == -1) return -1;
    if (kill(owned_pid, SIGTERM) == -1 && errno != ESRCH) return -1;
    for (attempt = 0; attempt < 50; ++attempt) {
        result = waitpid(owned_pid, &status, WNOHANG);
        if (result == owned_pid || (result == -1 && errno == ECHILD)) {
            owned_pid = -1;
            return 0;
        }
        if (result == -1 && errno != EINTR) return -1;
        brief_sleep();
    }
    if (kill(owned_pid, SIGKILL) == -1 && errno != ESRCH) return -1;
    for (attempt = 0; attempt < 50; ++attempt) {
        result = waitpid(owned_pid, &status, WNOHANG);
        if (result == owned_pid || (result == -1 && errno == ECHILD)) {
            owned_pid = -1;
            return 0;
        }
        if (result == -1 && errno != EINTR) return -1;
        brief_sleep();
    }
    return -1;
}

static void cleanup_at_exit(void) {
    if (reap_owned() == -1) fputs("faultlab: owned child cleanup incomplete\n", stderr);
}

static void interrupted(void) {
    if (stop_signal) {
        fprintf(stderr, "faultlab: interrupted by signal %d; output is diagnostic, not successful native evidence\n", (int)stop_signal);
        exit(128 + (int)stop_signal);
    }
}

static void json_text(const char *text) {
    const unsigned char *p = (const unsigned char *)text;
    putchar('"');
    for (; *p; ++p) {
        if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
        else if (*p < 32) printf("\\u%04x", (unsigned)*p);
        else putchar(*p);
    }
    putchar('"');
}

static const char *error_name(int error) {
    switch (error) {
    case 0: return "";
    case ETIMEDOUT: return "ETIMEDOUT";
    case ESRCH: return "ESRCH";
    case EBADF: return "EBADF";
    case EINTR: return "EINTR";
    case EINVAL: return "EINVAL";
    case EACCES: return "EACCES";
    case EIO: return "EIO";
    case ENOMEM: return "ENOMEM";
    case EAGAIN: return "EAGAIN";
    default: return "EUNKNOWN";
    }
}

static const char *observed_outcome(const struct observation *o) {
    if (o->rc == 0) return "reply";
    if (o->error == ETIMEDOUT) return "timeout";
    if (o->error == ESRCH || o->error == EBADF) return "server_gone";
    return "error";
}

static void event(const char *scenario, const char *phase, const char *outcome,
                  const char *detail, const struct observation *observation) {
    interrupted(); /* Includes cancellation accepted during the last owned-child reap. */
    uint64_t timestamp = observation ? observation->ended : now_ns();
    printf("{\"type\":\"event\",\"seq\":%u,\"scenario\":", ++sequence);
    json_text(scenario);
    fputs(",\"phase\":", stdout); json_text(phase);
    printf(",\"monotonic_ns\":%" PRIu64 ",\"outcome\":", timestamp);
    json_text(outcome);
    fputs(",\"errno_name\":", stdout);
    json_text(observation ? error_name(observation->error) : "");
    fputs(",\"detail\":", stdout); json_text(detail);
    if (observation) {
        printf(",\"started_ns\":%" PRIu64 ",\"duration_ns\":%" PRIu64 ",\"payload_ok\":%s",
               observation->started, observation->ended - observation->started,
               observation->payload_ok ? "true" : "false");
    }
    fputs("}\n", stdout);
    if (fflush(stdout) == EOF) {
        perror("faultlab: capture write");
        exit(2);
    }
    interrupted();
}

static void example_service(int ready_fd, int mode) {
    uint32_t message = 0;
    uint32_t reply = REPLY_TOKEN;
    int channel, receive_id;
    signal(SIGINT, SIG_DFL);
    signal(SIGTERM, SIG_DFL);
    signal(SIGPIPE, SIG_DFL);
    channel = ChannelCreate(0); /* No UNBLOCK flag: TimerTimeout must unblock client. */
    if (channel == -1) _exit(70);
    if (write(ready_fd, &channel, sizeof(channel)) != (ssize_t)sizeof(channel)) _exit(71);
    close(ready_fd);
    do { receive_id = MsgReceive(channel, &message, sizeof(message), NULL); }
    while (receive_id == 0); /* Ignore pulses; this example expects a full request. */
    if (receive_id < 0 || message != TOKEN) _exit(72);
    if (mode == 2) _exit(42); /* Exit after receive, before reply: expected ESRCH. */
    if (mode == 1) for (;;) pause(); /* Deliberate stall; parent times out and reaps. */
    if (MsgReply(receive_id, 0, &reply, sizeof(reply)) == -1) _exit(73);
    (void)ChannelDestroy(channel);
    _exit(0);
}

static int spawn_service(int mode, int *channel) {
    int ready[2];
    struct pollfd poller;
    ssize_t count;
    int result;
    if (owned_pid > 0) { errno = EBUSY; return -1; }
    if (pipe(ready) == -1) return -1;
    owned_pid = fork();
    if (owned_pid == 0) {
        close(ready[0]);
        example_service(ready[1], mode);
        _exit(74);
    }
    if (owned_pid == -1) {
        int saved = errno;
        close(ready[0]); close(ready[1]); errno = saved;
        return -1;
    }
    close(ready[1]);
    poller.fd = ready[0]; poller.events = POLLIN; poller.revents = 0;
    result = poll(&poller, 1, (int)timeout_ms + 1000);
    if (result <= 0 || !(poller.revents & POLLIN)) {
        int saved = result == 0 ? ETIMEDOUT : (result == -1 ? errno : EIO);
        close(ready[0]); errno = saved; return -1;
    }
    /* The owned child writes one small atomic int, then closes the pipe. */
    count = read(ready[0], channel, sizeof(*channel));
    close(ready[0]);
    if (count != (ssize_t)sizeof(*channel)) { errno = EIO; return -1; }
    return 0;
}

static int exchange(int mode, struct observation *o) {
    uint32_t request = TOKEN, reply = 0;
    uint64_t timeout = (uint64_t)timeout_ms * UINT64_C(1000000);
    struct sigevent notify;
    int channel, connection, saved;
    memset(o, 0, sizeof(*o));
    interrupted();
    if (spawn_service(mode, &channel) == -1) return -1;
    interrupted();
    connection = ConnectAttach(0, owned_pid, channel, _NTO_SIDE_CHANNEL, 0);
    if (connection == -1) return -1;
    SIGEV_UNBLOCK_INIT(&notify);
    o->started = now_ns();
    /* Arm immediately before the specific blocking call. */
    if (TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_SEND | _NTO_TIMEOUT_REPLY,
                     &notify, &timeout, NULL) == -1) {
        saved = errno; (void)ConnectDetach(connection); errno = saved; return -1;
    }
    o->rc = MsgSend(connection, &request, sizeof(request), &reply, sizeof(reply));
    o->error = o->rc == -1 ? errno : 0;
    o->ended = now_ns();
    o->payload_ok = o->rc == 0 && reply == REPLY_TOKEN;
    (void)ConnectDetach(connection);
    interrupted();
    return 0;
}

static int drill(const char *name, int mode) {
    struct observation initial, recovery;
    char detail[160];
    int matches;
    event(name, "begin", "started", "Isolated FaultLab-owned sample only", NULL);
    if (exchange(mode, &initial) == -1) {
        perror("faultlab: sample setup or timeout configuration");
        return -1;
    }
    snprintf(detail, sizeof(detail), "Owned sample pid=%ld; MsgSend rc=%d errno=%d",
             (long)owned_pid, initial.rc, initial.error);
    event(name, "request", observed_outcome(&initial), detail, &initial);
    matches = mode == 0 ? initial.rc == 0 && initial.payload_ok :
              mode == 1 ? initial.rc == -1 && initial.error == ETIMEDOUT :
                          initial.rc == -1 && initial.error == ESRCH;
    if (reap_owned() == -1) {
        event(name, "cleanup", "error", "Owned sample cleanup did not complete", NULL);
        return -1;
    }
    if (mode != 0) {
        if (exchange(0, &recovery) == -1) {
            perror("faultlab: recovery sample setup");
            return -1;
        }
        snprintf(detail, sizeof(detail), "Fresh owned sample pid=%ld; MsgSend rc=%d errno=%d",
                 (long)owned_pid, recovery.rc, recovery.error);
        event(name, "recovery_request", observed_outcome(&recovery), detail, &recovery);
        matches = matches && recovery.rc == 0 && recovery.payload_ok;
        if (reap_owned() == -1) {
            event(name, "cleanup", "error", "Recovery sample cleanup did not complete", NULL);
            return -1;
        }
    }
    event(name, "cleanup", "clean", "All owned sample children reaped", NULL);
    event(name, "end", "complete", "Drill observations complete; analyzer applies pinned contract", NULL);
    return matches ? 0 : 1;
}

int main(int argc, char **argv) {
    struct utsname identity;
    struct sigaction action;
    uint64_t session_start;
    int healthy, stall, exited;
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("Usage: faultlab_probe [--timeout-ms 10..5000]\nRuns healthy/stall/exit against disposable owned children; emits NDJSON.");
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--version") == 0) { puts(TOOL_VERSION); return 0; }
    if (argc != 1) {
        char *end = NULL;
        long value;
        if (argc != 3 || strcmp(argv[1], "--timeout-ms") != 0) {
            fputs("faultlab: expected --timeout-ms 10..5000 or --help\n", stderr);
            return 2;
        }
        errno = 0; value = strtol(argv[2], &end, 10);
        if (errno || end == argv[2] || *end || value < 10 || value > 5000) {
            fputs("faultlab: timeout must be an integer in 10..5000 ms\n", stderr);
            return 2;
        }
        timeout_ms = (unsigned)value;
    }
    if (uname(&identity) == -1) { perror("faultlab: uname"); return 2; }
    if (strcmp(identity.sysname, "QNX") != 0 || strncmp(identity.release, "8.", 2) != 0) {
        fputs("faultlab: this native runner requires QNX 8.x\n", stderr);
        return 2;
    }
    memset(&action, 0, sizeof(action));
    action.sa_handler = request_stop;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) == -1 || sigaction(SIGTERM, &action, NULL) == -1) {
        perror("faultlab: sigaction"); return 2;
    }
    /* EPIPE must reach the checked write path and atexit's owned-child cleanup. */
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &action, NULL) == -1) { perror("faultlab: SIGPIPE policy"); return 2; }
    if (atexit(cleanup_at_exit) != 0) return 2;
    session_start = now_ns();
    printf("{\"type\":\"session\",\"schema_version\":1,\"tool_version\":\"" TOOL_VERSION
           "\",\"session_id\":\"qnx-%ld-%" PRIu64 "\",\"source_kind\":\"qnx-native\",\"sysname\":",
           (long)getpid(), session_start);
    json_text(identity.sysname);
    fputs(",\"release\":", stdout); json_text(identity.release);
    fputs(",\"machine\":", stdout); json_text(identity.machine);
    printf(",\"timeout_ms\":%u,\"clock\":\"CLOCK_MONOTONIC\"}\n", timeout_ms);
    if (fflush(stdout) == EOF) return 2;
    healthy = drill("healthy", 0);
    if (healthy == -1) return 2;
    stall = drill("stall", 1);
    if (stall == -1) return 2;
    exited = drill("exit", 2);
    if (exited == -1) return 2;
    interrupted();
    return healthy || stall || exited ? 1 : 0;
}
