"""Tests for PortAllocator"""
import threading
import time
from backend.core.port_allocator import PortAllocator, PortExhaustedError, PF_BASE_PORT, PF_MAX_PORT


def test_acquire_and_release():
    alloc = PortAllocator(PF_BASE_PORT, PF_BASE_PORT + 99)
    p1 = alloc.acquire()
    assert PF_BASE_PORT <= p1 <= PF_BASE_PORT + 99
    assert alloc.in_use == 1
    assert alloc.available == 99

    p2 = alloc.acquire()
    assert p2 != p1
    assert alloc.in_use == 2

    alloc.release(p1)
    assert alloc.in_use == 1

    alloc.release(p2)
    assert alloc.in_use == 0


def test_idempotent_release():
    alloc = PortAllocator(PF_BASE_PORT, PF_BASE_PORT + 10)
    p = alloc.acquire()
    alloc.release(p)
    alloc.release(p)  # should not raise
    alloc.release(p + 999)  # releasing unallocated port should be safe


def test_exhaustion():
    alloc = PortAllocator(40000, 40002)  # only 3 ports
    alloc.acquire()
    alloc.acquire()
    alloc.acquire()
    try:
        alloc.acquire()
        assert False, "Should have raised PortExhaustedError"
    except PortExhaustedError:
        pass


def test_concurrent_safety():
    alloc = PortAllocator(PF_BASE_PORT, PF_BASE_PORT + 49)
    acquired = []
    errors = []

    def worker():
        try:
            p = alloc.acquire()
            acquired.append(p)
            time.sleep(0.01)
            alloc.release(p)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert len(errors) == 0, f"Concurrent errors: {errors}"
    assert alloc.in_use == 0, f"Leaked {alloc.in_use} ports"


def test_stats():
    alloc = PortAllocator(40000, 40004)
    stats = alloc.stats()
    assert stats["base"] == 40000
    assert stats["max"] == 40004
    assert stats["in_use"] == 0
    assert stats["available"] == 5
    assert stats["capacity"] == 5

    alloc.acquire()
    stats = alloc.stats()
    assert stats["in_use"] == 1
    assert stats["available"] == 4


def test_reset():
    alloc = PortAllocator(40000, 40004)
    alloc.acquire()
    alloc.acquire()
    assert alloc.in_use == 2
    alloc.reset()
    assert alloc.in_use == 0
    assert alloc.available == 5


def test_is_allocated():
    alloc = PortAllocator(40000, 40004)
    p = alloc.acquire()
    assert alloc.is_allocated(p)
    assert not alloc.is_allocated(99999)
    alloc.release(p)
    assert not alloc.is_allocated(p)
