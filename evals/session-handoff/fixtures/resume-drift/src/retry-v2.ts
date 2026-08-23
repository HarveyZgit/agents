export type RetryPolicy = {
  maxAttempts: number;
};

export async function runWithRetry<T>(operation: () => Promise<T>, policy: RetryPolicy): Promise<T> {
  return operation();
}
