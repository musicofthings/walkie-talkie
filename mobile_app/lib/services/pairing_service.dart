import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/pairing_session.dart';
import 'crypto_helper.dart';
import 'session_store.dart';

class PairingService {
  WebSocketChannel? _channel;

  Future<bool> pairWithData(String qrJson) async {
    try {
      final qrPayload = jsonDecode(qrJson);
      if (qrPayload is! Map) throw Exception('QR payload is not a JSON object');

      final wsUrl = qrPayload['ws_url'];
      if (wsUrl == null || wsUrl is! String) {
        throw Exception('Missing ws_url in pairing payload');
      }
      final desktopPublicKeyB64 = qrPayload['desktop_public_key'];
      if (desktopPublicKeyB64 == null || desktopPublicKeyB64 is! String) {
        throw Exception('Missing desktop_public_key in pairing payload');
      }

      final (:keyPair, :publicKeyBytes) = await CryptoHelper.generateKeyPair();
      final clientPublicKeyB64 = base64Url.encode(publicKeyBytes);

      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      await _channel!.ready;

      _channel!.sink.add(jsonEncode({
        'type': 'pair',
        'payload': {
          'device_id': _deviceId(),
          'device_name': 'Mozhi Mobile',
          'client_public_key': clientPublicKeyB64,
        },
      }));

      final raw = await _channel!.stream.first;
      final responseStr = raw is String ? raw : utf8.decode(raw as List<int>);
      final ackMessage = jsonDecode(responseStr);
      if (ackMessage is! Map) throw Exception('Unexpected server response format');

      final msgType = ackMessage['type'];
      if (msgType != 'pair_ack') {
        final errMsg = ackMessage['message'] ?? msgType ?? 'unknown error';
        throw Exception('Pairing rejected by server: $errMsg');
      }

      final ackPayload = ackMessage['payload'];
      if (ackPayload is! Map) throw Exception('pair_ack missing payload');

      final sessionToken = ackPayload['session_token'];
      if (sessionToken == null || sessionToken is! String) {
        throw Exception('pair_ack missing session_token');
      }

      final desktopPubKeyBytes = base64Url.decode(
        desktopPublicKeyB64.padRight(
          desktopPublicKeyB64.length + (4 - desktopPublicKeyB64.length % 4) % 4,
          '=',
        ),
      );
      final aesKey = await CryptoHelper.deriveAesKey(keyPair, desktopPubKeyBytes);
      final aesKeyBytes = await aesKey.extractBytes();

      final session = PairingSession(
        wsUrl: wsUrl,
        desktopPublicKey: desktopPublicKeyB64,
        clientPrivateKey: await keyPair.extractPrivateKeyBytes(),
        clientPublicKey: publicKeyBytes,
        sharedSecret: aesKeyBytes,
        sessionToken: sessionToken,
      );
      SessionStore.instance.save(session);

      return true;
    } catch (e) {
      await _channel?.sink.close();
      _channel = null;
      rethrow;
    }
  }

  WebSocketChannel? get channel => _channel;

  Future<void> disconnect() async {
    await _channel?.sink.close();
    _channel = null;
    SessionStore.instance.clear();
  }

  String _deviceId() =>
      'mozhi-mobile-${DateTime.now().millisecondsSinceEpoch}';
}
