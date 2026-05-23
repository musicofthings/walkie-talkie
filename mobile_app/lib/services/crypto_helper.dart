import 'dart:convert';

import 'package:cryptography/cryptography.dart';

/// Cryptographic helpers for X25519 key exchange and AES-GCM transport.
class CryptoHelper {
  CryptoHelper._();

  static final _x25519 = X25519();
  static final _hkdf = Hkdf(hmac: Hmac.sha256(), outputLength: 32);
  static final _aesGcm = AesGcm.with256bits(nonceLength: 12);

  /// Generate an X25519 key pair and return (privateKey, publicKeyBytes).
  static Future<({SimpleKeyPair keyPair, List<int> publicKeyBytes})>
      generateKeyPair() async {
    final keyPair = await _x25519.newKeyPair();
    final publicKey = await keyPair.extractPublicKey();
    return (keyPair: keyPair, publicKeyBytes: publicKey.bytes);
  }

  /// Derive a 32-byte AES key from the X25519 shared secret using HKDF.
  static Future<SecretKey> deriveAesKey(
    SimpleKeyPair clientKeyPair,
    List<int> serverPublicKeyBytes,
  ) async {
    final serverPublicKey = SimplePublicKey(serverPublicKeyBytes, type: KeyPairType.x25519);
    final sharedSecret = await _x25519.sharedSecretKey(
      keyPair: clientKeyPair,
      remotePublicKey: serverPublicKey,
    );
    final sharedSecretBytes = await sharedSecret.extractBytes();

    // HKDF derivation — MUST match desktop info=b"mozhi-audio-transport"
    final derived = await _hkdf.deriveKey(
      secretKey: SecretKey(sharedSecretBytes),
      info: utf8.encode('mozhi-audio-transport'),
      nonce: const <int>[], // empty salt — matches desktop salt=None
    );
    return derived;
  }

  /// Encrypt plaintext bytes with AES-GCM, returning (nonceB64, ciphertextB64).
  static Future<({String nonceB64, String ciphertextB64})> encrypt(
    SecretKey aesKey,
    List<int> plaintext,
  ) async {
    final secretBox = await _aesGcm.encrypt(
      plaintext,
      secretKey: aesKey,
    );
    final nonceB64 = base64Url.encode(secretBox.nonce);
    // ciphertext + mac concatenated (AES-GCM standard)
    final ciphertextB64 = base64Url.encode(secretBox.concatenation(nonce: false));
    return (nonceB64: nonceB64, ciphertextB64: ciphertextB64);
  }
}
