/**
 * Present only so the import resolves. `Platform.OS` is 'web' in tests, so
 * `lib/storage.ts` never calls any of this — if one of these ever throws in a
 * test run, the storage layer took the native branch by mistake.
 */
export async function getItemAsync(): Promise<string | null> {
  throw new Error('SecureStore reached in a test: storage took the native branch.');
}

export async function setItemAsync(): Promise<void> {
  throw new Error('SecureStore reached in a test: storage took the native branch.');
}

export async function deleteItemAsync(): Promise<void> {
  throw new Error('SecureStore reached in a test: storage took the native branch.');
}
