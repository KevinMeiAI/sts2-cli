using HarmonyLib;
using MegaCrit.Sts2.Core.Events.Custom.CrystalSphereEvent;
using MegaCrit.Sts2.Core.Nodes.Events.Custom.CrystalSphere;

namespace Sts2Headless;

public partial class RunSimulator
{
    private CrystalSphereMinigame? _crystalSphere;
    private Task? _pendingCrystalReveal;
    private bool HasPendingCrystalSphere => _crystalSphere is { IsFinished: false };

    private static void PatchCrystalSphereScreen()
    {
        // Replace only the Godot screen. Native placement, fog, divination costs,
        // reveal effects, completion and rewards all remain in the engine.
        new Harmony("sts2headless.crystalsphere").Patch(
            AccessTools.Method(typeof(NCrystalSphereScreen), "ShowScreen"),
            prefix: new HarmonyMethod(typeof(RunSimulator), nameof(CrystalSphereScreenPrefix)));
    }

    private static bool CrystalSphereScreenPrefix(CrystalSphereMinigame __0, ref NCrystalSphereScreen? __result)
    {
        var sim = LocPatches._bundleSimRef ?? throw new InvalidOperationException("No active simulator");
        sim._crystalSphere = __0;
        __result = null;
        return false;
    }

    private Dictionary<string, object?> CrystalSphereState()
    {
        var game = _crystalSphere!;
        var rows = new List<List<Dictionary<string, object?>>>();
        for (int y = 0; y < game.GridSize.Y; y++)
        {
            var row = new List<Dictionary<string, object?>>();
            for (int x = 0; x < game.GridSize.X; x++)
            {
                var cell = game.cells[x, y];
                var view = new Dictionary<string, object?> { ["x"] = x, ["y"] = y, ["hidden"] = cell.IsHidden };
                // Never expose the contents, position or size of an item behind fog.
                // A visible fragment identifies its category, like the on-screen image.
                if (!cell.IsHidden)
                    view["item_type"] = cell.Item?.GetType().Name;
                row.Add(view);
            }
            rows.Add(row);
        }
        return new()
        {
            ["type"] = "decision", ["decision"] = "crystal_sphere", ["context"] = RunContext(),
            ["divinations_remaining"] = game.DivinationCount,
            ["width"] = game.GridSize.X, ["height"] = game.GridSize.Y,
            ["tools"] = new[] { "small", "big" },
            ["instructions"] = "Reveal a hidden cell. Small clears one cell; big clears its 3x3 neighborhood. Each costs one divination. Fully uncover items to obtain their effects.",
            ["grid"] = rows, ["player"] = PlayerSummary(_runState!.Players[0]),
        };
    }

    private Dictionary<string, object?> DoCrystalSphereReveal(Dictionary<string, object?>? args)
    {
        if (!HasPendingCrystalSphere) return Error("No Crystal Sphere grid is pending");
        if (args == null || !args.ContainsKey("x") || !args.ContainsKey("y"))
            return Error("crystal_sphere_reveal requires x, y and optional tool (small or big)");
        var x = Convert.ToInt32(args["x"]);
        var y = Convert.ToInt32(args["y"]);
        var tool = args.GetValueOrDefault("tool")?.ToString() ?? "big";
        var game = _crystalSphere!;
        if (x < 0 || y < 0 || x >= game.GridSize.X || y >= game.GridSize.Y)
            return Error("Crystal Sphere cell is out of bounds");
        if (tool is not ("small" or "big")) return Error("Crystal Sphere tool must be small or big");
        if (!game.cells[x, y].IsHidden) return Error("Crystal Sphere cell is already revealed");
        game.SetTool((CrystalSphereMinigame.CrystalSphereToolType)(tool == "big" ? 2 : 1));
        // Completing the last click can synchronously enter a card reward choice.
        _pendingCrystalReveal = Task.Run(() => game.CellClicked(game.cells[x, y]));
        return DetectDecisionPoint();
    }

    private Dictionary<string, object?>? SettleCrystalReveal()
    {
        var task = _pendingCrystalReveal;
        if (task == null) return null;
        var deadline = Environment.TickCount64 + 5000;
        while (!task.IsCompleted)
        {
            _syncCtx.Pump();
            if (_cardSelector.HasPending || _cardSelector.HasPendingReward) return null;
            if (Environment.TickCount64 >= deadline) return Error("Crystal Sphere reveal is still pending; query get_state");
            Thread.Sleep(1);
        }
        _pendingCrystalReveal = null;
        try { task.GetAwaiter().GetResult(); return null; }
        catch (Exception ex) { return ErrorWithTrace("Crystal Sphere reveal failed", ex); }
    }
}
