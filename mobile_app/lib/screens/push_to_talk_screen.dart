import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/audio_stream_service.dart';
import '../services/pairing_service.dart';
import '../services/tts_service.dart';
import 'qr_scan_screen.dart';

enum _Speaker { user, claude }

class _ChatMessage {
  final _Speaker speaker;
  final String text;
  final DateTime time;
  _ChatMessage(this.speaker, this.text) : time = DateTime.now();
}

class PushToTalkScreen extends StatefulWidget {
  const PushToTalkScreen({super.key});

  @override
  State<PushToTalkScreen> createState() => _PushToTalkScreenState();
}

class _PushToTalkScreenState extends State<PushToTalkScreen>
    with SingleTickerProviderStateMixin {
  final PairingService _pairingService = PairingService();
  final AudioStreamService _audioService = AudioStreamService();
  final TtsService _ttsService = TtsService();
  final ScrollController _scrollCtrl = ScrollController();

  StreamSubscription<dynamic>? _wsSub;

  bool _paired = false;
  bool _streaming = false;
  bool _claudeThinking = false;
  String? _error;

  final List<_ChatMessage> _messages = [];

  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _ttsService.init();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    )..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.18).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  void _subscribeWs() {
    _wsSub?.cancel();
    final stream = _pairingService.events;
    if (stream == null) return;
    _wsSub = stream.listen((raw) {
      try {
        final msg = jsonDecode(
          raw is String ? raw : utf8.decode(raw as List<int>),
        ) as Map<String, dynamic>;

        switch (msg['type']) {
          case 'transcript':
            final text = (msg['text'] as String?)?.trim() ?? '';
            if (text.isNotEmpty) {
              setState(() => _messages.add(_ChatMessage(_Speaker.user, text)));
              _scrollToBottom();
            }

          case 'tts':
            final text = (msg['text'] as String?)?.trim() ?? '';
            if (text.isNotEmpty) {
              _ttsService.speak(text);
              setState(() {
                _claudeThinking = false;
                _messages.add(_ChatMessage(_Speaker.claude, text));
              });
              _scrollToBottom();
            }
        }
      } catch (_) {}
    });
  }

  Future<void> _pair() async {
    setState(() => _error = null);

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
    _wsSub?.cancel();
    _wsSub = null;
    await _pairingService.disconnect();
    if (!mounted) return;
    setState(() {
      _paired = false;
      _streaming = false;
      _claudeThinking = false;
      _messages.clear();
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
        setState(() => _claudeThinking = true);
      }
    } catch (e) {
      debugPrint('PTT error: $e');
      if (mounted) setState(() => _error = 'Streaming error: $e');
    }
    if (!mounted) return;
    setState(() => _streaming = active);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _wsSub?.cancel();
    _pulseCtrl.dispose();
    _scrollCtrl.dispose();
    _audioService.dispose();
    _ttsService.dispose();
    _pairingService.disconnect();
    super.dispose();
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF111318),
      appBar: _buildAppBar(),
      body: Column(
        children: [
          if (_error != null) _buildErrorBanner(),
          Expanded(child: _paired ? _buildChatList() : _buildUnpairedState()),
          if (_paired) _buildInputArea(),
        ],
      ),
    );
  }

  AppBar _buildAppBar() {
    return AppBar(
      backgroundColor: const Color(0xFF1A1D24),
      title: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _paired ? Colors.greenAccent : Colors.grey,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            _paired ? 'WalkieTalkie · Connected' : 'WalkieTalkie',
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
          ),
        ],
      ),
      actions: [
        if (_paired)
          IconButton(
            icon: const Icon(Icons.link_off, size: 20),
            tooltip: 'Disconnect',
            onPressed: _unpair,
          ),
      ],
    );
  }

  Widget _buildErrorBanner() {
    return Material(
      color: const Color(0xFF3B1212),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            const Icon(Icons.error_outline, color: Colors.redAccent, size: 16),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _error!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              ),
            ),
            GestureDetector(
              onTap: () => setState(() => _error = null),
              child: const Icon(Icons.close, color: Colors.redAccent, size: 16),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUnpairedState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.sensors_off, size: 56, color: Colors.grey),
          const SizedBox(height: 16),
          const Text(
            'Not paired',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: Colors.white70),
          ),
          const SizedBox(height: 8),
          const Text(
            'Scan the QR code displayed on your desktop to connect',
            style: TextStyle(color: Colors.grey, fontSize: 14),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 28),
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: Colors.teal,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            ),
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('Scan Desktop QR'),
            onPressed: _pair,
          ),
        ],
      ),
    );
  }

  Widget _buildChatList() {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: _messages.length + (_claudeThinking ? 1 : 0),
      itemBuilder: (context, i) {
        if (i == _messages.length) return _buildThinkingBubble();
        return _buildBubble(_messages[i]);
      },
    );
  }

  Widget _buildBubble(_ChatMessage msg) {
    final isUser = msg.speaker == _Speaker.user;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? const Color(0xFF00796B) : const Color(0xFF262A34),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment:
              isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Text(
              isUser ? 'You' : 'Claude',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: isUser ? Colors.teal[100] : Colors.blue[200],
              ),
            ),
            const SizedBox(height: 4),
            Text(
              msg.text,
              style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4),
            ),
            const SizedBox(height: 2),
            Text(
              _formatTime(msg.time),
              style: TextStyle(fontSize: 10, color: Colors.white.withValues(alpha: 0.4)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildThinkingBubble() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: const BoxDecoration(
          color: Color(0xFF262A34),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomRight: Radius.circular(16),
            bottomLeft: Radius.circular(4),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Claude',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: Colors.blue[200],
              ),
            ),
            const SizedBox(width: 8),
            _ThinkingDots(),
          ],
        ),
      ),
    );
  }

  Widget _buildInputArea() {
    return Container(
      color: const Color(0xFF1A1D24),
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            _streaming
                ? 'Listening…'
                : _claudeThinking
                    ? 'Claude is thinking…'
                    : 'Hold to speak',
            style: TextStyle(
              color: _streaming ? Colors.redAccent : Colors.grey,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 12),
          Listener(
            onPointerDown: (_) => _togglePtt(true),
            onPointerUp: (_) => _togglePtt(false),
            onPointerCancel: (_) => _togglePtt(false),
            child: _streaming
                ? ScaleTransition(
                    scale: _pulseAnim,
                    child: _micButton(),
                  )
                : _micButton(),
          ),
        ],
      ),
    );
  }

  Widget _micButton() {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: _streaming ? Colors.red : Colors.teal,
        boxShadow: _streaming
            ? [
                BoxShadow(
                  color: Colors.red.withValues(alpha: 0.45),
                  blurRadius: 20,
                  spreadRadius: 4,
                ),
              ]
            : null,
      ),
      child: const Icon(Icons.mic, size: 32, color: Colors.white),
    );
  }

  String _formatTime(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

// Animated "..." dots to show while Claude is generating a response.
class _ThinkingDots extends StatefulWidget {
  @override
  State<_ThinkingDots> createState() => _ThinkingDotsState();
}

class _ThinkingDotsState extends State<_ThinkingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) {
        final phase = (_ctrl.value * 3).floor();
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            return Container(
              width: 6,
              height: 6,
              margin: const EdgeInsets.symmetric(horizontal: 2),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: i == phase ? 0.9 : 0.25),
              ),
            );
          }),
        );
      },
    );
  }
}
