#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <optional>
#include <string>

#include "tick_buffer.hpp"

namespace py = pybind11;
using namespace py::literals;
using polywhirl::TickBuffer;

namespace {

using DoubleArray = py::array_t<double, py::array::c_style | py::array::forcecast>;
using Int64Array = py::array_t<std::int64_t, py::array::c_style | py::array::forcecast>;

constexpr const char* kColumns[] = {"mid", "spread", "imbalance", "timestamp", "volume"};

py::array_t<double> field_array(const TickBuffer& b, TickBuffer::Field f) {
    py::array_t<double> out(static_cast<py::ssize_t>(b.size()));
    b.copy_field(f, out.mutable_data());
    return out;
}

py::array_t<std::int64_t> timestamp_array(const TickBuffer& b) {
    py::array_t<std::int64_t> out(static_cast<py::ssize_t>(b.size()));
    b.copy_timestamps(out.mutable_data());
    return out;
}

// (size, 5) float64 matrix in COLUMNS order. ms timestamps (~1.8e12) are well
// below 2**53, so they survive the cast to double exactly.
py::array_t<double> to_numpy(const TickBuffer& b) {
    const auto n = static_cast<py::ssize_t>(b.size());
    py::array_t<double> out(std::vector<py::ssize_t>{n, 5});
    auto r = out.mutable_unchecked<2>();
    for (py::ssize_t i = 0; i < n; ++i) {
        const auto t = b.at(static_cast<std::size_t>(i));
        r(i, 0) = t.mid;
        r(i, 1) = t.spread;
        r(i, 2) = t.imbalance;
        r(i, 3) = static_cast<double>(t.timestamp);
        r(i, 4) = t.volume;
    }
    return out;
}

void extend(TickBuffer& b, const DoubleArray& mid, const DoubleArray& spread,
            const DoubleArray& imbalance, const Int64Array& timestamp,
            const std::optional<DoubleArray>& volume) {
    const py::ssize_t n = mid.size();
    for (const py::array* a : {static_cast<const py::array*>(&mid), static_cast<const py::array*>(&spread),
                               static_cast<const py::array*>(&imbalance),
                               static_cast<const py::array*>(&timestamp)}) {
        if (a->ndim() != 1 || a->size() != n)
            throw std::invalid_argument("all inputs must be 1-D arrays of the same length");
    }
    if (volume && (volume->ndim() != 1 || volume->size() != n))
        throw std::invalid_argument("volume must be a 1-D array of the same length");

    auto m = mid.unchecked<1>();
    auto s = spread.unchecked<1>();
    auto im = imbalance.unchecked<1>();
    auto ts = timestamp.unchecked<1>();
    for (py::ssize_t i = 0; i < n; ++i) {
        b.push(m(i), s(i), im(i), ts(i), volume ? volume->at(i) : 0.0);
    }
}

std::size_t normalize_index(const TickBuffer& b, py::ssize_t i) {
    const auto n = static_cast<py::ssize_t>(b.size());
    if (i < 0) i += n;
    if (i < 0 || i >= n) throw py::index_error("TickBuffer index out of range");
    return static_cast<std::size_t>(i);
}

}  // namespace

PYBIND11_MODULE(_tickbuffer, m) {
    m.doc() = "C++ ring buffer of order-book ticks with numpy feature export.";

    py::tuple columns(std::size(kColumns));
    for (std::size_t i = 0; i < std::size(kColumns); ++i) columns[i] = kColumns[i];
    m.attr("COLUMNS") = columns;

    py::class_<TickBuffer>(m, "TickBuffer",
                           "Ring buffer of the last N (mid, spread, imbalance, timestamp, volume) ticks.")
        .def(py::init<std::size_t>(), "capacity"_a)
        .def("push", &TickBuffer::push, "mid"_a, "spread"_a, "imbalance"_a, "timestamp"_a,
             "volume"_a = 0.0, "Append one tick, overwriting the oldest when full.")
        .def("extend", &extend, "mid"_a, "spread"_a, "imbalance"_a, "timestamp"_a,
             "volume"_a = py::none(), "Append ticks from equal-length 1-D arrays.")
        .def("clear", &TickBuffer::clear)
        .def("__len__", &TickBuffer::size)
        .def("__getitem__",
             [](const TickBuffer& b, py::ssize_t i) {
                 const auto t = b.at(normalize_index(b, i));
                 return py::make_tuple(t.mid, t.spread, t.imbalance, t.timestamp, t.volume);
             })
        .def("__repr__",
             [](const TickBuffer& b) {
                 return "TickBuffer(size=" + std::to_string(b.size()) +
                        ", capacity=" + std::to_string(b.capacity()) + ")";
             })
        .def_property_readonly("capacity", &TickBuffer::capacity)
        .def_property_readonly("full", &TickBuffer::full)

        // Scalar features of the latest state
        .def("vwap", &TickBuffer::vwap, "n"_a,
             "Volume-weighted average mid over the last n ticks; NaN if they have no volume.")
        .def("mid_zscore", &TickBuffer::mid_zscore, "window"_a,
             "z-score of the latest mid vs. the last `window` mids; NaN until `window` ticks.")
        .def("imbalance_ewma", &TickBuffer::imbalance_ewma, "alpha"_a,
             "EWMA of imbalance over the buffer, seeded with the oldest tick.")

        // Per-tick feature series, aligned with the buffer (oldest first)
        .def(
            "mid_zscore_series",
            [](const TickBuffer& b, std::size_t window) {
                py::array_t<double> out(static_cast<py::ssize_t>(b.size()));
                b.mid_zscore_series(window, out.mutable_data());
                return out;
            },
            "window"_a)
        .def(
            "imbalance_ewma_series",
            [](const TickBuffer& b, double alpha) {
                py::array_t<double> out(static_cast<py::ssize_t>(b.size()));
                b.imbalance_ewma_series(alpha, out.mutable_data());
                return out;
            },
            "alpha"_a)

        // Raw columns as numpy arrays (copies, oldest first)
        .def("mids", [](const TickBuffer& b) { return field_array(b, TickBuffer::Field::Mid); })
        .def("spreads", [](const TickBuffer& b) { return field_array(b, TickBuffer::Field::Spread); })
        .def("imbalances",
             [](const TickBuffer& b) { return field_array(b, TickBuffer::Field::Imbalance); })
        .def("volumes", [](const TickBuffer& b) { return field_array(b, TickBuffer::Field::Volume); })
        .def("timestamps", &timestamp_array)
        .def("to_numpy", &to_numpy, "(size, 5) float64 matrix with columns in COLUMNS order.");
}
