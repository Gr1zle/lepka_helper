import 'dart:convert';
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

void ensureInitialized() {
  // Stock Flet wire diagnostics include control attributes. Never log protected
  // session records in a release APK, while preserving other diagnostics.
  if (kReleaseMode) {
    final original = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {
      if (message != null && (message.startsWith('WS message:') || message.startsWith('InvokeMethodAction:'))) return;
      original(message, wrapWidth: wrapWidth);
    };
  }
}

Widget? createControl(CreateControlArgs args) {
  return args.control.type == 'lepka_protected_session'
      ? ProtectedSession(control: args.control, backend: args.backend)
      : null;
}

class ProtectedSession extends StatefulWidget {
  final Control control;
  final FletControlBackend backend;
  const ProtectedSession({super.key, required this.control, required this.backend});
  @override State<ProtectedSession> createState() => _ProtectedSessionState();
}
class _ProtectedSessionState extends State<ProtectedSession> {
  static const channel = MethodChannel('ru.gr1zle.lepka/protected_session');
  String last = '';
  Future<void> run(String command) async {
    String requestId = '';
    try {
      final decoded = jsonDecode(command) as Map<String, dynamic>;
      requestId = decoded['requestId'] as String;
      final operation = decoded['operation'] as String;
      if (!['read', 'write', 'delete', 'notifyStatus', 'notifyPermission', 'notifySync', 'notifyClear', 'notifyOpen', 'notifyShow', 'notifyTest'].contains(operation)) throw const FormatException();
      final value = await channel.invokeMethod<String>(operation, {'value': decoded['value']});
      widget.backend.triggerControlEvent(widget.control.id, 'result', jsonEncode({'requestId': requestId, 'ok': true, 'value': value}));
    } catch (_) {
      widget.backend.triggerControlEvent(widget.control.id, 'result', jsonEncode({'requestId': requestId, 'ok': false}));
    }
  }
  @override Widget build(BuildContext context) {
    final command = widget.control.attrString('command', '')!;
    if (command.isNotEmpty && command != last) {
      last = command;
      WidgetsBinding.instance.addPostFrameCallback((_) => run(command));
    }
    return const SizedBox.shrink();
  }
}
