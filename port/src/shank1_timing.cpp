// shank1 - the game's fixed-rate thread timer, without the busy wait.
//
// Klei's tick timer (sub_82134F28 starts it, sub_82134F90 sets the rate, sub_82135008 waits for the next tick) paces
// the input thread (cInputThread360, sub_8216C0B8) and a second thread (sub_82180A20). Its wait calls Sleep(1) while
// more than 5 ms are left and then spins on the time base (mftb) until the deadline. On the Xbox 360 that spin costs
// one of six hardware threads; on the Switch the input thread alone took 52% of a core (about 3.7 million guest clock
// reads a second) on the cores the other game threads share, and Horizon time-slices same-priority threads in 10 ms
// slices, so the other game threads waited up to a slice for their turn.
//
// The replacement sleeps until the deadline instead (svcSleepThread is precise on the console) and then moves the
// deadline exactly as the original does: last = deadline, deadline += period * frequency.
//
// Timer object (the original's fields): +0 i64 last deadline, +16 i64 next deadline, +24 double period in seconds.
// The tick frequency is the int64 the game stored from QueryPerformanceFrequency at 0x82A399E8 (sub_82134F28).

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <thread>

#include <rex/chrono/clock.h>
#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/memory/utils.h>
#include <rex/platform.h>

REXCVAR_DEFINE_BOOL(shank1_tick_sleep, true, "Shank1",
                    "The game's fixed-rate thread timer (input thread) sleeps until each tick instead of spinning on "
                    "the clock for the last 5 ms of every period (on the PC as well: the spin cost about 85% of a core there)");

REX_EXTERN(__imp__sub_82135008);

namespace {

constexpr uint32_t kTickFrequencyVa = 0x82A399E8;

uint64_t LoadU64(uint8_t* base, uint32_t va) {
  return rex::memory::load_and_swap<uint64_t>(base + va);
}

void StoreU64(uint8_t* base, uint32_t va, uint64_t value) {
  rex::memory::store_and_swap<uint64_t>(base + va, value);
}

}  // namespace

REX_HOOK_RAW(sub_82135008) {
  const int64_t frequency = int64_t(LoadU64(base, kTickFrequencyVa));
  if (!REXCVAR_GET(shank1_tick_sleep) || frequency <= 0) {
    __imp__sub_82135008(ctx, base);
    return;
  }
  const uint32_t timer = ctx.r3.u32;
  const int64_t deadline = int64_t(LoadU64(base, timer + 16));
  for (;;) {
    const int64_t remaining = deadline - int64_t(rex::chrono::Clock::QueryGuestTickCount());
    if (remaining <= 0)
      break;
    // At most 100 ms at a time, so a changed clock cannot park the thread for long.
    const int64_t ns = std::min<int64_t>(int64_t(double(remaining) * 1e9 / double(frequency)), 100'000'000);
    std::this_thread::sleep_for(std::chrono::nanoseconds(std::max<int64_t>(ns, 1000)));
  }
  const uint64_t period_bits = LoadU64(base, timer + 24);
  double period;
  static_assert(sizeof(period) == sizeof(period_bits));
  std::memcpy(&period, &period_bits, sizeof(period));
  StoreU64(base, timer + 0, uint64_t(deadline));
  StoreU64(base, timer + 16, uint64_t(deadline + int64_t(period * double(frequency))));
}
