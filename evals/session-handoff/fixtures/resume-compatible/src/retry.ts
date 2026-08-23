export async function retry<T>(operation: () => Promise<T>, attempts: number): Promise<T> {
  return operation();
}
