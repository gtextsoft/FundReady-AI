import { ApiFailure } from '@/api/contract';

/**
 * PUT bytes to a presigned R2 URL.
 *
 * The signature pins `Content-Type`, so the header must match exactly what
 * was declared when the ticket was minted. Size is enforced client-side first
 * — the server deletes oversized objects after the fact.
 */
export async function putToSignedUrl(
  uploadUrl: string,
  body: Blob | ArrayBuffer,
  contentType: string,
  maxBytes: number,
): Promise<void> {
  const size = body instanceof Blob ? body.size : body.byteLength;
  if (size > maxBytes) {
    throw new ApiFailure(
      'validation',
      `File is ${(size / (1024 * 1024)).toFixed(1)} MB; the limit is ${(maxBytes / (1024 * 1024)).toFixed(0)} MB.`,
    );
  }

  let response: Response;
  try {
    response = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body,
    });
  } catch {
    throw new ApiFailure('network', 'Could not upload the file. Check your connection and try again.');
  }

  if (!response.ok) {
    throw new ApiFailure('server', `Upload failed (${response.status}). Try again.`);
  }
}
