/**
 * Lightweight in-memory cache with TTL and stale-while-revalidate.
 * Used for auth profile and saved-recipes to avoid redundant API calls.
 */

type CacheEntry<T> = {
  data: T;
  fetchedAt: number;
  ttlMs: number;
};

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export function cacheGet<T>(key: string): T | null {
  const entry = store.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > entry.ttlMs) {
    store.delete(key);
    return null;
  }
  return entry.data;
}

export function cacheSet<T>(key: string, data: T, ttlMs: number): void {
  store.set(key, { data, fetchedAt: Date.now(), ttlMs });
}

export function cacheInvalidate(prefix?: string): void {
  if (!prefix) {
    store.clear();
    return;
  }
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key);
  }
}

/**
 * Fetch with deduplication: concurrent callers share one in-flight request.
 * Returns cached data when fresh; optionally returns stale data while revalidating.
 */
export async function cacheFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  options: { ttlMs?: number; staleMs?: number } = {}
): Promise<T> {
  const ttlMs = options.ttlMs ?? 60_000;
  const staleMs = options.staleMs ?? ttlMs * 2;
  const entry = store.get(key) as CacheEntry<T> | undefined;
  const age = entry ? Date.now() - entry.fetchedAt : Infinity;

  if (entry && age < ttlMs) {
    return entry.data;
  }

  if (entry && age < staleMs) {
    if (!inflight.has(key)) {
      inflight.set(
        key,
        fetcher()
          .then((data) => {
            cacheSet(key, data, ttlMs);
            return data;
          })
          .finally(() => inflight.delete(key))
      );
    }
    return entry.data;
  }

  if (inflight.has(key)) {
    return inflight.get(key) as Promise<T>;
  }

  const promise = fetcher()
    .then((data) => {
      cacheSet(key, data, ttlMs);
      return data;
    })
    .finally(() => inflight.delete(key));

  inflight.set(key, promise);
  return promise;
}
