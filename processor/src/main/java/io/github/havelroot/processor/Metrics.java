package io.github.havelroot.processor;

import java.util.concurrent.atomic.AtomicLong;

/** Contadores expostos em /health. */
public final class Metrics {

    private final long startedAt = System.nanoTime();
    private final AtomicLong processed = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();
    private final AtomicLong totalMillis = new AtomicLong();

    public void success(long millis) {
        processed.incrementAndGet();
        totalMillis.addAndGet(millis);
    }

    public void failure() {
        failed.incrementAndGet();
    }

    public long processed() {
        return processed.get();
    }

    public long failed() {
        return failed.get();
    }

    public long averageMillis() {
        long count = processed.get();
        return count == 0 ? 0 : Math.round((double) totalMillis.get() / count);
    }

    public long uptimeSeconds() {
        return (System.nanoTime() - startedAt) / 1_000_000_000L;
    }
}
