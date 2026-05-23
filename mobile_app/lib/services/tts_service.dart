import 'package:flutter_tts/flutter_tts.dart';

/// Wraps flutter_tts for on-device speech synthesis.
class TtsService {
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.5);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    _ready = true;
  }

  Future<void> speak(String text) async {
    if (!_ready || text.trim().isEmpty) return;
    await _tts.stop();
    await _tts.speak(text);
  }

  Future<void> stop() async => _tts.stop();

  void dispose() {
    _tts.stop();
  }
}
