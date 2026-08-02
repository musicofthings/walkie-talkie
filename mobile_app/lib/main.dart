import 'package:flutter/material.dart';
import 'screens/push_to_talk_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const WalkieTalkieApp());
}

class WalkieTalkieApp extends StatelessWidget {
  const WalkieTalkieApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WalkieTalkie',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.teal,
        brightness: Brightness.dark,
      ),
      home: const PushToTalkScreen(),
    );
  }
}
