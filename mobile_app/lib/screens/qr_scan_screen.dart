import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

class QrScanScreen extends StatefulWidget {
  const QrScanScreen({super.key});

  @override
  State<QrScanScreen> createState() => _QrScanScreenState();
}

class _QrScanScreenState extends State<QrScanScreen> {
  bool _handled = false;
  bool _manualMode = true; // default to manual — camera crashes on x86 simulator
  final _textController = TextEditingController();

  void _onDetect(BarcodeCapture capture) {
    if (_handled) return;
    final String? value = capture.barcodes.firstOrNull?.rawValue;
    if (value == null || value.isEmpty) return;
    _handled = true;
    Navigator.of(context).pop(value);
  }

  void _submitManual() {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    Navigator.of(context).pop(text);
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_manualMode ? 'Enter Pairing JSON' : 'Scan Desktop Pairing QR'),
        actions: [
          TextButton(
            onPressed: () => setState(() => _manualMode = !_manualMode),
            child: Text(
              _manualMode ? 'Use Camera' : 'Enter Manually',
              style: const TextStyle(color: Colors.white),
            ),
          ),
        ],
      ),
      body: _manualMode ? _buildManualEntry() : _buildScanner(),
    );
  }

  Widget _buildScanner() {
    return MobileScanner(onDetect: _onDetect);
  }

  Widget _buildManualEntry() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Paste the pairing JSON from the desktop terminal.\n\nRun the desktop agent and copy the JSON shown after the QR code:',
            style: TextStyle(fontSize: 14, color: Colors.white70),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _textController,
            maxLines: 6,
            decoration: const InputDecoration(
              hintText: '{"ws_url": "ws://...", "desktop_public_key": "..."}',
              border: OutlineInputBorder(),
            ),
            style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _submitManual,
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}
