import 'dart:convert';
import 'dart:async';
import 'package:flet/src/controls/create_control.dart' as fletControls;
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter/material.dart';

void ensureInitialized() {
  // Stock Flet wire diagnostics include control attributes. Never log protected
  // session records in a release APK, while preserving other diagnostics.
  if (kReleaseMode) {
    final original = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {
      if (message != null &&
          (message.startsWith('WS message:') ||
              message.startsWith('InvokeMethodAction:')))
        return;
      original(message, wrapWidth: wrapWidth);
    };
  }
}

Widget? createControl(CreateControlArgs args) {
  if (args.control.type == 'lepka_refresh') return LepkaRefresh(args: args);
  return args.control.type == 'lepka_protected_session'
      ? ProtectedSession(control: args.control, backend: args.backend)
      : null;
}

class ProtectedSession extends StatefulWidget {
  final Control control;
  final FletControlBackend backend;
  const ProtectedSession({
    super.key,
    required this.control,
    required this.backend,
  });
  @override
  State<ProtectedSession> createState() => _ProtectedSessionState();
}

class _ProtectedSessionState extends State<ProtectedSession> {
  static const channel = MethodChannel('ru.gr1zle.lepka/protected_session');
  String last = '';
  String lastUi = '';
  Future<void> run(String command) async {
    String requestId = '';
    try {
      final decoded = jsonDecode(command) as Map<String, dynamic>;
      requestId = decoded['requestId'] as String;
      final operation = decoded['operation'] as String;
      if (![
        'read',
        'write',
        'delete',
        'notifyStatus',
        'notifyPermission',
        'notifySync',
        'notifyClear',
        'notifyOpen',
        'notifyShow',
        'notifyTest',
        'fileSave',
        'cameraCapture',
      ].contains(operation))
        throw const FormatException();
      final value = await channel.invokeMethod<String>(operation, {
        'value': decoded['value'],
      });
      widget.backend.triggerControlEvent(
        widget.control.id,
        'result',
        jsonEncode({'requestId': requestId, 'ok': true, 'value': value}),
      );
    } catch (_) {
      widget.backend.triggerControlEvent(
        widget.control.id,
        'result',
        jsonEncode({'requestId': requestId, 'ok': false}),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final command = widget.control.attrString('command', '')!;
    if (command.isNotEmpty && command != last) {
      last = command;
      WidgetsBinding.instance.addPostFrameCallback((_) => run(command));
    }
    final uiCommand = widget.control.attrString('uiCommand', '')!;
    if (uiCommand.isNotEmpty && uiCommand != lastUi) {
      lastUi = uiCommand;
      WidgetsBinding.instance.addPostFrameCallback((_) => run(uiCommand));
    }
    return const SizedBox.shrink();
  }
}

class LepkaRefresh extends StatefulWidget {
  final CreateControlArgs args;
  const LepkaRefresh({super.key, required this.args});
  @override
  State<LepkaRefresh> createState() => _LepkaRefreshState();
}

class _LepkaRefreshState extends State<LepkaRefresh> {
  Completer<void>? pending;
  String request = '';
  int sequence = 0;
  @override
  void didUpdateWidget(covariant LepkaRefresh oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.args.control.attrString('refreshDone') == request &&
        pending != null &&
        !pending!.isCompleted)
      pending!.complete();
  }

  @override
  void dispose() {
    if (pending != null && !pending!.isCompleted) pending!.complete();
    super.dispose();
  }

  Future<void> refresh() async {
    if (pending != null && !pending!.isCompleted) return;
    pending = Completer<void>();
    request = '${++sequence}';
    widget.args.backend.triggerControlEvent(
      widget.args.control.id,
      'refresh',
      request,
    );
    try {
      await pending!.future.timeout(
        const Duration(seconds: 20),
        onTimeout: () {},
      );
    } finally {
      if (pending != null && !pending!.isCompleted) pending!.complete();
      pending = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final args = widget.args;
    final children = args.children.where(
      (c) => c.name == 'content' && c.isVisible,
    );
    if (children.isEmpty) return const SizedBox.shrink();
    return fletControls.constrainedControl(
      context,
      RefreshIndicator(
        onRefresh: refresh,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: fletControls.createControl(
            args.control,
            children.first.id,
            args.parentDisabled,
            parentAdaptive: args.parentAdaptive,
          ),
        ),
      ),
      args.parent,
      args.control,
    );
  }
}
