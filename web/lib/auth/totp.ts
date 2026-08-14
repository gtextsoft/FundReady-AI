/** Browser TOTP (RFC 6238) so enrolment can confirm a scanned QR without typing. */

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function decodeBase32(secret: string): Uint8Array<ArrayBuffer> {
  const cleaned = secret.toUpperCase().replace(/[\s=-]+/g, "");
  let bits = "";
  for (const char of cleaned) {
    const value = ALPHABET.indexOf(char);
    if (value < 0) continue;
    bits += value.toString(2).padStart(5, "0");
  }
  const bytes = new Uint8Array(Math.floor(bits.length / 8));
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(bits.slice(i * 8, i * 8 + 8), 2);
  }
  return bytes;
}

export async function totpCode(secret: string, at: number = Date.now()): Promise<string> {
  const key = decodeBase32(secret);
  const counter = Math.floor(at / 1000 / 30);
  const buffer = new ArrayBuffer(8);
  new DataView(buffer).setUint32(4, counter);
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"],
  );
  const hmac = new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, buffer));
  const offset = hmac[hmac.length - 1]! & 0x0f;
  const truncated =
    ((hmac[offset]! & 0x7f) << 24) |
    ((hmac[offset + 1]! & 0xff) << 16) |
    ((hmac[offset + 2]! & 0xff) << 8) |
    (hmac[offset + 3]! & 0xff);
  return String(truncated % 1_000_000).padStart(6, "0");
}
