import 'package:flutter_tts/flutter_tts.dart';

/// Wraps flutter_tts for on-device speech synthesis.
///
/// Configured for streamed, sentence-by-sentence playback: the desktop agent
/// sends Claude's reply in chunks as it is generated, so utterances are QUEUED
/// (not flushed) and play back in order. Call [flush] to interrupt for a new
/// turn (barge-in).
class TtsService {
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.5);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
    await _tts.setQueueMode(1); // QUEUE_ADD: enqueue chunks instead of interrupting
    _ready = true;
  }

  /// Enqueue a chunk of Claude's reply. Chunks play sequentially.
  Future<void> speak(String text) async {
    if (!_ready || text.trim().isEmpty) return;
    await _tts.speak(text);
  }

  /// Interrupt current playback and clear the queue (barge-in / new user turn).
  Future<void> flush() async => _tts.stop();

  Future<void> stop() async => _tts.stop();

  void dispose() {
    _tts.stop();
  }
}
