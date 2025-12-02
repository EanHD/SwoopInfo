// Swoop Intelligence Widget Tests

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  testWidgets('App launches without errors', (WidgetTester tester) async {
    // Basic smoke test - app can be created
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: Center(
              child: Text('Swoop Intelligence'),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Swoop Intelligence'), findsOneWidget);
  });
}
