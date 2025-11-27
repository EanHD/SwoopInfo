import 'package:flutter_test/flutter_test.dart';
import 'package:swoop_intelligence/models/chunk.dart';

void main() {
  test('parses quarantined unavailable chunk correctly', () {
    final json = {
      "content_id": "test_content",
      "chunk_type": "spec",
      "status": "unavailable",
      "verification_status": "pending_verification",
      "qa_status": "pending",
      "verified_status": "unverified",
      "visibility": "quarantined",
      "data": {
        "message": "Data is currently being verified for accuracy.",
        "reason": "data_not_verified",
      },
    };

    final chunk = Chunk.fromJson(
      json,
      vehicleId: 'test_vehicle',
      templateType: 'test_template',
      title: 'Test Chunk',
    );

    expect(chunk.isReady, isFalse);
    expect(chunk.isQuarantined, isTrue);
    expect(chunk.isBanned, isFalse);
  });

  test('parses banned chunk correctly', () {
    final json = {
      "content_id": "test_content",
      "chunk_type": "spec",
      "status": "unavailable",
      "verification_status": "rejected",
      "qa_status": "fail",
      "verified_status": "banned",
      "visibility": "banned",
      "data": {"message": "Data has been rejected by QA."},
    };

    final chunk = Chunk.fromJson(
      json,
      vehicleId: 'test_vehicle',
      templateType: 'test_template',
      title: 'Test Chunk',
    );

    expect(chunk.isBanned, isTrue);
    expect(chunk.isQuarantined, isFalse);
  });

  test('parses unverified but visible chunk correctly', () {
    final json = {
      "content_id": "test_content",
      "chunk_type": "procedure",
      "status": "ready",
      "verification_status": "pending_verification",
      "qa_status": "pending",
      "verified_status": "unverified",
      "visibility": "safe",
      "data": {"steps": []},
    };

    final chunk = Chunk.fromJson(
      json,
      vehicleId: 'test_vehicle',
      templateType: 'test_template',
      title: 'Test Chunk',
    );

    expect(chunk.isReady, isTrue);
    expect(chunk.isQuarantined, isFalse);
    expect(chunk.isBanned, isFalse);
    expect(chunk.verifiedStatus, equals('unverified'));
    expect(chunk.visibility, equals('safe'));
  });
}
