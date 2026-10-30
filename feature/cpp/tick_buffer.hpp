#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace polywhirl {

struct Tick {
    double mid;
    double spread;
    double imbalance;
    std::int64_t timestamp;  // exchange timestamp, ms
    double volume;
};

// Fixed-capacity ring buffer of the last N order-book ticks.
//
// Storage is struct-of-arrays: each field lives in its own contiguous vector, so
// exporting a field to numpy is at most two block copies (before and after the
// wrap point) instead of a strided gather over an array of structs.
//
// Logical index 0 is the oldest tick, size() - 1 the newest. Not thread-safe.
class TickBuffer {
public:
    enum class Field { Mid, Spread, Imbalance, Volume };

    static constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
    // Below this the window is treated as flat and the z-score is 0. Polymarket
    // ticks are >= 0.001, so any real move gives a far larger std.
    static constexpr double kMinStd = 1e-9;

    explicit TickBuffer(std::size_t capacity)
        : capacity_(capacity),
          mid_(capacity),
          spread_(capacity),
          imbalance_(capacity),
          volume_(capacity),
          timestamp_(capacity) {
        if (capacity == 0) throw std::invalid_argument("capacity must be positive");
    }

    void push(double mid, double spread, double imbalance, std::int64_t timestamp,
              double volume = 0.0) {
        mid_[head_] = mid;
        spread_[head_] = spread;
        imbalance_[head_] = imbalance;
        timestamp_[head_] = timestamp;
        volume_[head_] = volume;
        head_ = (head_ + 1) % capacity_;
        if (size_ < capacity_) ++size_;
    }

    void clear() noexcept { head_ = size_ = 0; }

    std::size_t size() const noexcept { return size_; }
    std::size_t capacity() const noexcept { return capacity_; }
    bool full() const noexcept { return size_ == capacity_; }

    Tick at(std::size_t i) const {
        if (i >= size_) throw std::out_of_range("TickBuffer index out of range");
        const std::size_t p = physical(i);
        return {mid_[p], spread_[p], imbalance_[p], timestamp_[p], volume_[p]};
    }

    // Copy a field, oldest first, into `out` (must hold size() elements).
    void copy_field(Field f, double* out) const { copy_out(field(f), out); }
    void copy_timestamps(std::int64_t* out) const { copy_out(timestamp_, out); }

    // Volume-weighted average mid over the last n ticks. NaN if they carry no volume.
    double vwap(std::size_t n) const {
        n = std::min(n, size_);
        double pv = 0.0, v = 0.0;
        for (std::size_t i = size_ - n; i < size_; ++i) {
            const std::size_t p = physical(i);
            pv += mid_[p] * volume_[p];
            v += volume_[p];
        }
        return v > 0.0 ? pv / v : kNaN;
    }

    // z-score of the latest mid against the last `window` mids (sample std).
    // NaN until the buffer holds `window` ticks.
    double mid_zscore(std::size_t window) const {
        check_window(window);
        if (size_ < window) return kNaN;
        const std::size_t first = size_ - window;
        double mean = 0.0;
        for (std::size_t i = first; i < size_; ++i) mean += mid_[physical(i)];
        mean /= static_cast<double>(window);
        double ss = 0.0;
        for (std::size_t i = first; i < size_; ++i) {
            const double d = mid_[physical(i)] - mean;
            ss += d * d;
        }
        const double sd = std::sqrt(ss / static_cast<double>(window - 1));
        const double last = mid_[physical(size_ - 1)];
        return sd > kMinStd ? (last - mean) / sd : 0.0;
    }

    // Rolling mid z-score for every tick, O(size) via sliding sums.
    void mid_zscore_series(std::size_t window, double* out) const {
        check_window(window);
        if (size_ == 0) return;
        const double w = static_cast<double>(window);
        // Shift by the first mid so the running sums stay small and the
        // sumsq - sum^2/w subtraction loses less precision.
        const double ref = mid_[physical(0)];
        double sum = 0.0, sumsq = 0.0;
        for (std::size_t i = 0; i < size_; ++i) {
            const double x = mid_[physical(i)] - ref;
            sum += x;
            sumsq += x * x;
            if (i >= window) {
                const double old = mid_[physical(i - window)] - ref;
                sum -= old;
                sumsq -= old * old;
            }
            if (i + 1 < window) {
                out[i] = kNaN;
                continue;
            }
            const double mean = sum / w;
            const double sd = std::sqrt(std::max(0.0, (sumsq - sum * mean) / (w - 1.0)));
            out[i] = sd > kMinStd ? (x - mean) / sd : 0.0;
        }
    }

    // EWMA of imbalance over the whole buffer, seeded with the oldest tick.
    double imbalance_ewma(double alpha) const {
        check_alpha(alpha);
        if (size_ == 0) return kNaN;
        double e = imbalance_[physical(0)];
        for (std::size_t i = 1; i < size_; ++i) e += alpha * (imbalance_[physical(i)] - e);
        return e;
    }

    void imbalance_ewma_series(double alpha, double* out) const {
        check_alpha(alpha);
        if (size_ == 0) return;
        double e = imbalance_[physical(0)];
        out[0] = e;
        for (std::size_t i = 1; i < size_; ++i) {
            e += alpha * (imbalance_[physical(i)] - e);
            out[i] = e;
        }
    }

private:
    std::size_t start() const noexcept { return (head_ + capacity_ - size_) % capacity_; }
    std::size_t physical(std::size_t i) const noexcept { return (start() + i) % capacity_; }

    const std::vector<double>& field(Field f) const {
        switch (f) {
            case Field::Mid: return mid_;
            case Field::Spread: return spread_;
            case Field::Imbalance: return imbalance_;
            case Field::Volume: return volume_;
        }
        throw std::invalid_argument("unknown field");
    }

    template <typename T>
    void copy_out(const std::vector<T>& src, T* out) const {
        const std::size_t s = start();
        const std::size_t first = std::min(size_, capacity_ - s);
        std::copy_n(src.data() + s, first, out);
        std::copy_n(src.data(), size_ - first, out + first);
    }

    static void check_window(std::size_t window) {
        if (window < 2) throw std::invalid_argument("window must be >= 2");
    }

    static void check_alpha(double alpha) {
        if (!(alpha > 0.0 && alpha <= 1.0)) throw std::invalid_argument("alpha must be in (0, 1]");
    }

    std::size_t capacity_;
    std::size_t head_ = 0;  // next write slot
    std::size_t size_ = 0;
    std::vector<double> mid_, spread_, imbalance_, volume_;
    std::vector<std::int64_t> timestamp_;
};

}  // namespace polywhirl
