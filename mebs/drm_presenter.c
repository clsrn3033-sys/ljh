/* Minimal exclusive DRM/KMS dumb-buffer presenter, no X11/EGL/Mesa.
 * Protocol: tightly packed 800x480 BGRX frames on stdin, complete frames only.
 * No device discovery/driver assumption: caller names card, connected exact mode.
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm.h>
#include <drm_mode.h>

static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped = 1; }
int main(int argc, char **argv) {
    const unsigned width = 800, height = 480;
    int fd = -1, result = 1;
    drmModeRes *resources = NULL;
    drmModeConnector *connector = NULL;
    drmModeCrtc *saved = NULL;
    drmModeModeInfo mode;
    uint32_t crtc = 0, fb = 0;
    struct drm_mode_create_dumb create = {0};
    void *mapping = MAP_FAILED;
    unsigned char *frame = NULL;
    if (argc != 2) { fprintf(stderr, "Usage: mebs-drm /dev/dri/cardN\n"); return 2; }
    signal(SIGINT, stop); signal(SIGTERM, stop);
    fd = open(argv[1], O_RDWR | O_CLOEXEC);
    if (fd < 0 || drmSetMaster(fd)) { perror("DRM master"); goto done; }
    uint64_t cap = 0;
    if (drmGetCap(fd, DRM_CAP_DUMB_BUFFER, &cap) || !cap) goto done;
    resources = drmModeGetResources(fd);
    if (!resources) goto done;
    for (int i = 0; i < resources->count_connectors && !connector; ++i) {
        drmModeConnector *candidate = drmModeGetConnector(fd, resources->connectors[i]);
        if (!candidate) continue;
        if (candidate->connection == DRM_MODE_CONNECTED) {
            for (int m = 0; m < candidate->count_modes; ++m) {
                if (candidate->modes[m].hdisplay != width || candidate->modes[m].vdisplay != height) continue;
                for (int e = 0; e < candidate->count_encoders && !crtc; ++e) {
                    drmModeEncoder *encoder = drmModeGetEncoder(fd, candidate->encoders[e]);
                    if (!encoder) continue;
                    for (int c = 0; c < resources->count_crtcs; ++c) {
                        if (encoder->possible_crtcs & (1U << c)) {
                            crtc = resources->crtcs[c]; break;
                        }
                    }
                    drmModeFreeEncoder(encoder);
                }
                if (crtc) { mode = candidate->modes[m]; connector = candidate; break; }
            }
        }
        if (!connector) drmModeFreeConnector(candidate);
    }
    if (!connector || !crtc) { fprintf(stderr, "No connected 800x480 DRM mode\n"); goto done; }
    saved = drmModeGetCrtc(fd, crtc);
    create.width = width; create.height = height; create.bpp = 32;
    if (ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create)) goto done;
    if (drmModeAddFB(fd, width, height, 24, 32, create.pitch, create.handle, &fb)) goto done;
    struct drm_mode_map_dumb map = { .handle = create.handle };
    if (ioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map)) goto done;
    mapping = mmap(NULL, create.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
    if (mapping == MAP_FAILED) goto done;
    memset(mapping, 0, create.size);
    if (drmModeSetCrtc(fd, crtc, fb, 0, 0, &connector->connector_id, 1, &mode)) goto done;
    fprintf(stdout, "READY 800 480\n"); fflush(stdout);
    frame = malloc(width * height * 4);
    if (!frame) goto done;
    while (!stopped) {
        size_t offset = 0, bytes = width * height * 4;
        while (offset < bytes && !stopped) {
            ssize_t count = read(STDIN_FILENO, frame + offset, bytes - offset);
            if (count == 0) { result = 0; goto done; }
            if (count < 0) { if (errno == EINTR) continue; goto done; }
            offset += (size_t)count;
        }
        if (stopped) break;
        /* Single scanout, no claim of tear-free 60 FPS until target measurement. */
        for (unsigned y = 0; y < height; ++y)
            memcpy((unsigned char *)mapping + y * create.pitch, frame + y * width * 4, width * 4);
    }
    result = 0;
done:
    if (saved && connector) {
        if (saved->mode_valid)
            drmModeSetCrtc(fd, saved->crtc_id, saved->buffer_id, saved->x, saved->y, &connector->connector_id, 1, &saved->mode);
        else drmModeSetCrtc(fd, saved->crtc_id, 0, 0, 0, NULL, 0, NULL);
    }
    free(frame);
    if (mapping != MAP_FAILED) munmap(mapping, create.size);
    if (fb) drmModeRmFB(fd, fb);
    if (create.handle) { struct drm_mode_destroy_dumb destroy = { .handle = create.handle }; ioctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy); }
    if (saved) drmModeFreeCrtc(saved);
    if (connector) drmModeFreeConnector(connector);
    if (resources) drmModeFreeResources(resources);
    if (fd >= 0) { drmDropMaster(fd); close(fd); }
    return result;
}
