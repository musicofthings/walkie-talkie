import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/audio_stream_service.dart';
import '../services/pairing_service.dart';
import '../services/tts_service.dart';
import 'qr_scan_screen.dart';

class PushToTalkScreen extends StatefulWidget {
  const PushToTalkScreen({super.key});

  @override
  State<PushToTalkScreen> createState() => _PushToTalkScreenState();
}

class _PushToTalkScreenState extends State<PushToTalkScreen> {
  final PairingService _pairingService = PairingService();
  final AudioStreamService _audioService = AudioStreamService();
  final TtsService _ttsService = TtsService();

  StreamSubscription<dynamic>? _wsSub;

  bool _paired = false;
  bool _streaming = false;
  String? _error;
  String? _lastResponse;

  @override
  void initState() {
    super.initState();
    _ttsService.init();
  }

  void _subscribeWs() {
    final channel = _pairingService.channel;
    if (channel == null) return;
    _wsSub = channel.stream.listen((raw) {
      try {
        final msg = jsonDecode(raw is String ? raw : utf8.decode(raw as List<int>));
        if (msg['type'] == 'tts') {
          final text = (msg['text'] as String?) ?? '';
          if (text.isNotEmpty) {
            _ttsService.speak(text);
            if (mounted) setState(() => _lastResponse = text);
          }
        }
      } catch (_) {}
    });
  }

  Future<void> _pair() async {
    setState(() => _error = null);

    // Navigate to QR scanner and get the scanned payload JSON
    final qrJson = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const QrScanScreen()),
    );
    if (qrJson == null || !mounted) return;

    try {
      final paired = await _pairingService.pairWithData(qrJson);
      if (!mounted) return;
      setState(() => _paired = paired);
      if (paired) _subscribeWs();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Pairing failed: $e');
    }
  }

  Future<void> _unpair() async {
    await _pairingService.disconnect();
    if (!mounted) return;
    setState(() {
      _paired = false;
      _streaming = false;
    });
  }

  Future<void> _togglePtt(bool active) async {
    if (!_paired) return;
    try {
      if (active) {
        final channel = _pairingService.channel;
        if (channel == null) {
          setState(() => _error = 'WebSocket not connected');
          return;
        }
        await _audioService.startStreaming(channel);
      } else {
        await _audioService.stopStreaming();
      }
    } catch (e) {
      debugPrint('PTT error: $e');
      if (mounted) setState(() => _error = 'Streaming error: $e');
    }
    if (!mounted) return;
    setState(() => _streaming = active);
  }

  @override
  void dispose() {
    _wsSub?.cancel();
    _audioService.dispose();
    _ttsService.dispose();
    _pairingService.disconnect();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mozhi Push-to-Talk'),
        actions: [
          if (_paired)
            IconButton(
              icon: const Icon(Icons.link_off),
              tooltip: 'Disconnect',
              onPressed: _unpair,
            ),
        ],
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              _paired ? Icons.check_circle : Icons.link_off,
              size: 32,
              color: _paired ? Colors.green : Colors.grey,
            ),
            const SizedBox(height: 8),
            Text(
              _paired
                  ? 'Paired with desktop ✅'
                  : 'Not paired — scan desktop QR',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: const TextStyle(color: Colors.red, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 24),
            if (!_paired)
              ElevatedButton.icon(
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Pair Desktop via QR'),
                onPressed: _pair,
              ),
            const SizedBox(height: 28),
            Listener(
              onPointerDown: (_) => _togglePtt(true),
              onPointerUp: (_) => _togglePtt(false),
              onPointerCancel: (_) => _togglePtt(false),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 120),
                width: _streaming ? 160 : 140,
                height: _streaming ? 160 : 140,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: !_paired
                      ? Colors.grey
                      : _streaming
                          ? Colors.red
                          : Colors.teal,
                  boxShadow: _streaming
                      ? [
                          const BoxShadow(
                            color: Color.fromARGB(100, 244, 67, 54),
                            blurRadius: 24,
                            spreadRadius: 4,
                          ),
                        ]
                      : null,
                ),
                child: const Icon(Icons.mic, size: 52, color: Colors.white),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              _streaming
                  ? 'Streaming audio…'
                  : 'Press and hold to stream audio securely',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (_lastResponse != null) ...[
              const SizedBox(height: 24),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  'Claude: $_lastResponse',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: Colors.teal),
                  textAlign: TextAlign.center,
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}