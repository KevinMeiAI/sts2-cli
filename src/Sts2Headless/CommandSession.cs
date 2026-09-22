using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Sts2Headless;

/// <summary>Exact CLI checkpoints, including unresolved choices and combat rewards.</summary>
internal sealed class CommandSession
{
    private const string Format = "sts2-cli-checkpoint";
    private readonly string _engineHash;
    private RunSimulator _sim = new();
    private readonly List<JsonElement> _commands = new();
    private static readonly HashSet<string> RecordedCommands = new()
        { "start_run", "load_save", "action", "set_player", "set_draw_order", "enter_room" };

    public CommandSession(string libDir)
    {
        using var stream = File.OpenRead(Path.Combine(libDir, "sts2.dll"));
        _engineHash = Convert.ToHexString(SHA256.HashData(stream));
    }

    public Dictionary<string, object?>? Execute(JsonElement command)
    {
        var kind = command.GetProperty("cmd").GetString();
        if (kind == "write_continue_save" || kind == "quit")
        {
            var path = command.TryGetProperty("path", out var p) ? p.GetString() : null;
            if (kind == "write_continue_save") return Save(path);
            var saved = string.IsNullOrEmpty(path) ? null : Save(path);
            if (saved != null && (!saved.TryGetValue("success", out var ok) || ok is not true))
                return new() { ["type"] = "save_error", ["save"] = saved };
            _sim.CleanUp();
            return new() { ["type"] = "quit_result", ["success"] = true, ["save"] = saved };
        }

        if (kind == "start_run")
        {
            // Persist a concrete seed even when callers request a random run.
            var node = JsonNode.Parse(command.GetRawText())!;
            if (node["seed"] == null || string.IsNullOrEmpty(node["seed"]!.GetValue<string>()))
                node["seed"] = Convert.ToHexString(RandomNumberGenerator.GetBytes(5));
            command = JsonSerializer.SerializeToElement(node);
        }
        if (kind == "load_save")
        {
            var json = command.TryGetProperty("json", out var j) ? j.GetString() : null;
            if (json == null && command.TryGetProperty("path", out var path))
                json = File.ReadAllText(path.GetString()!);
            if (json == null) return Error("Provide 'path' or 'json' for load_save");
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("format", out var format) && format.GetString() == Format)
                return Restore(doc.RootElement);
            // Inline native base saves so subsequent checkpoints never depend on an external file.
            command = JsonSerializer.SerializeToElement(new
            {
                cmd = "load_save", json,
                lang = command.TryGetProperty("lang", out var lang) ? lang.GetString() : "en",
            });
        }

        var result = Program.HandleCommand(_sim, command);
        if (kind is "start_run" or "load_save")
        {
            if (result?.GetValueOrDefault("type") as string == "error") return result;
            _commands.Clear();
        }
        // Keep erroring actions too: an action can commit side effects before reporting an error.
        if (kind != null && RecordedCommands.Contains(kind)) _commands.Add(command.Clone());
        return result;
    }

    private Dictionary<string, object?> Save(string? path)
    {
        if (string.IsNullOrEmpty(path)) return Error("No output path specified for checkpoint");
        if (_commands.Count == 0) return Error("No active run to save");
        var state = _sim.GetState();
        if (state.GetValueOrDefault("type") as string == "error") return state;
        string? temporary = null;
        try
        {
            var json = JsonSerializer.Serialize(new
            {
                format = Format, version = 1, engine_sha256 = _engineHash,
                commands = _commands, expected_state = state,
            });
            var fullPath = Path.GetFullPath(path);
            Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
            temporary = fullPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temporary, json);
            File.Move(temporary, fullPath, overwrite: true);
            return new() { ["type"] = "save_result", ["success"] = true, ["path"] = fullPath,
                ["size"] = json.Length, ["format"] = Format, ["decision"] = state.GetValueOrDefault("decision") };
        }
        catch (Exception ex) { return Error($"Checkpoint failed: {ex.Message}"); }
        finally { if (temporary != null && File.Exists(temporary)) File.Delete(temporary); }
    }

    private Dictionary<string, object?> Restore(JsonElement saved)
    {
        if (saved.GetProperty("version").GetInt32() != 1) return Error("Unsupported checkpoint version");
        if (saved.GetProperty("engine_sha256").GetString() != _engineHash)
            return Error("Checkpoint game engine does not match the installed engine");
        var commands = saved.GetProperty("commands").EnumerateArray().Select(c => c.Clone()).ToList();
        if (commands.Count == 0) return Error("Empty checkpoint");
        // Checkpoints may only replay game commands, never file writes or nested checkpoints.
        for (int i = 0; i < commands.Count; i++)
        {
            var cmd = commands[i];
            var kind = cmd.GetProperty("cmd").GetString() ?? "";
            if (!RecordedCommands.Contains(kind) ||
                (i == 0 ? kind is not ("start_run" or "load_save") : kind is "start_run" or "load_save"))
                return Error("Invalid command in checkpoint");
            if (kind == "load_save")
            {
                if (!cmd.TryGetProperty("json", out var native)) return Error("Checkpoint base save must be inline");
                using var doc = JsonDocument.Parse(native.GetString()!);
                if (!doc.RootElement.TryGetProperty("schema_version", out _)) return Error("Invalid native base save");
            }
        }
        if (_commands.Count > 0) _sim.CleanUp();
        _sim = new RunSimulator();
        _commands.Clear();
        try
        {
            foreach (var command in commands) Program.HandleCommand(_sim, command);
            var state = _sim.GetState();
            if (!JsonNode.DeepEquals(JsonSerializer.SerializeToNode(state),
                                    JsonNode.Parse(saved.GetProperty("expected_state").GetRawText())))
                throw new InvalidOperationException("Checkpoint replay diverged; the saved decision was not restored");
            _commands.AddRange(commands);
            return state;
        }
        catch (Exception ex)
        {
            _sim.CleanUp();
            _sim = new RunSimulator();
            return Error($"Checkpoint restore failed: {ex.Message}");
        }
    }

    private static Dictionary<string, object?> Error(string message) =>
        new() { ["type"] = "error", ["message"] = message };
}
