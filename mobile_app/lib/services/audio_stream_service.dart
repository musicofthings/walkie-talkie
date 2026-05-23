import 'dart:async';
import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'crypto_helper.dart';
import 'session_store.dart';

/// Captures microphone audio, encrypts it with AES-GCM, and streams
/// encrypted packets over the paired WebSocket connection.
class AudioStreamService {
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<List<int>>? _audioSub;
  WebSocketChannel? _channel;

  final _pcmBuffer = <int>[];

  /// ~1 second of PCM16 mono @ 16 kHz = 32 000 bytes
  static const int _chunkSize = 16000 * 2;

  /// Start capturing microphone audio and streaming encrypted packets.
  ///
  /// [channel] is the WebSocket already opened during pairing.
  Future<void> startStreaming(WebSocketChannel channel) async {
    final session = SessionStore.instance.session;
    if (session == null) {
      throw StateError('Not paired — call PairingService.pairWithData first');
    }

    _channel = channel;

    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      throw StateError(
        'Microphone permission denied. Go to Settings → Privacy → Microphone '
        'and enable access for this app.',
      );
    }

    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
    );

    _audioSub = stream.cast<List<int>>().listen((chunk) {
      _pcmBuffer.addAll(chunk);
      if (_pcmBuffer.length >= _chunkSize) {
        final bytes = List<int>.from(_pcmBuffer);
        _pcmBuffer.clear();
        _sendEncrypted(bytes, session.sessionToken, session.sharedSecret);
      }
    });
  }

  /// Stop streaming, flush remaining buffer, and release microphone.
  Future<void> stopStreaming() async {
    await _audioSub?.cancel();
    _audioSub = null;

    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }

    // Flush any remaining buffered audio
    final session = SessionStore.instance.session;
    if (_pcmBuffer.isNotEmpty && session != null) {
      final remaining = List<int>.from(_pcmBuffer);
      _pcmBuffer.clear();
      await _sendEncrypted(
        remaining,
        session.sessionToken,
        session.sharedSecret,
      );
    }
    _pcmBuffer.clear();

    // Signal desktop to flush its buffer
    _channel?.sink.add(jsonEncode({'type': 'flush'}));
  }

  /// Encrypt a PCM chunk and send it over the WebSocket.
  Future<void> _sendEncrypted(
    List<int> pcmBytes,
    String token,
    List<int> aesKeyBytes,
  ) async {
    if (_channel == null) return;

    final aesKey = SecretKeyData(aesKeyBytes);
    final (:nonceB64, :ciphertextB64) = await CryptoHelper.encrypt(
      aesKey,
      pcmBytes,
    );

    _channel!.sink.add(jsonEncode({
      'type': 'audio',
      'token': token,
      'payload': {
        'nonce': nonceB64,
        'ciphertext': ciphertextB64,
        'sent_at_ms': DateTime.now().millisecondsSinceEpoch,
      },
    }));
  }

  /// Release all resources.
  void dispose() {
    _audioSub?.cancel();
    _recorder.dispose();
    _pcmBuffer.clear();
  }
}
