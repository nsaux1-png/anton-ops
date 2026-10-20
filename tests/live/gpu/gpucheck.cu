// GPU check for the live tests (SOP-111). On every visible GPU: fill 4 GiB, run a kernel over it
// repeatedly for a few seconds, and check sample results against the CPU. One line per GPU.
// Exit code 1 if any GPU fails.  Build: nvcc -O2 -arch=sm_120 -o gpucheck gpucheck.cu
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#define CHECK(call)                                                                      \
    do {                                                                                 \
        cudaError_t err = (call);                                                        \
        if (err != cudaSuccess) {                                                        \
            printf("FAIL gpu=%d %s: %s\n", dev, #call, cudaGetErrorString(err));         \
            return false;                                                                \
        }                                                                                \
    } while (0)

__global__ void seed(uint32_t *x, size_t n) {
    for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n; i += (size_t)gridDim.x * blockDim.x)
        x[i] = (uint32_t)i;
}

__global__ void step(uint32_t *x, size_t n) {
    for (size_t i = blockIdx.x * (size_t)blockDim.x + threadIdx.x; i < n; i += (size_t)gridDim.x * blockDim.x)
        x[i] = x[i] * 1664525u + 1013904223u;
}

static uint32_t expected(uint32_t v, int steps) {
    for (int s = 0; s < steps; s++) v = v * 1664525u + 1013904223u;
    return v;
}

static bool check_gpu(int dev, double seconds) {
    CHECK(cudaSetDevice(dev));
    cudaDeviceProp p;
    CHECK(cudaGetDeviceProperties(&p, dev));
    char bus[32];
    CHECK(cudaDeviceGetPCIBusId(bus, sizeof bus, dev));

    const size_t n = (size_t)1 << 30;  // 4 GiB of 32-bit values
    uint32_t *x;
    CHECK(cudaMalloc(&x, n * sizeof *x));
    seed<<<4096, 256>>>(x, n);
    CHECK(cudaGetLastError());

    int steps = 0;
    auto start = std::chrono::steady_clock::now();
    do {
        step<<<4096, 256>>>(x, n);
        CHECK(cudaGetLastError());
        CHECK(cudaDeviceSynchronize());
        steps++;
    } while (std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() < seconds);

    const size_t samples[] = {0, 1, 12345, n / 3, n / 2, n - 1};
    for (size_t i : samples) {
        uint32_t v;
        CHECK(cudaMemcpy(&v, x + i, sizeof v, cudaMemcpyDeviceToHost));
        if (v != expected((uint32_t)i, steps)) {
            printf("FAIL gpu=%d bus=%s wrong result at %zu\n", dev, bus, i);
            cudaFree(x);
            return false;
        }
    }
    CHECK(cudaFree(x));
    printf("OK gpu=%d bus=%s cc=%d.%d mem_gib=%.1f steps=%d name=%s\n", dev, bus, p.major, p.minor,
           p.totalGlobalMem / 1073741824.0, steps, p.name);
    return true;
}

int main(int argc, char **argv) {
    double seconds = argc > 1 ? atof(argv[1]) : 5;
    int count = 0;
    if (cudaGetDeviceCount(&count) != cudaSuccess || count == 0) {
        printf("FAIL no GPUs visible\n");
        return 1;
    }
    printf("GPUS %d\n", count);
    bool ok = true;
    for (int dev = 0; dev < count; dev++) ok = check_gpu(dev, seconds) && ok;
    return ok ? 0 : 1;
}
