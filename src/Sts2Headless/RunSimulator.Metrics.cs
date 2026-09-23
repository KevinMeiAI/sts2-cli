using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Rooms;

namespace Sts2Headless;

public partial class RunSimulator
{
    private CombatState? _metricsCombat;
    private readonly List<Creature> _metricsEnemies = new();

    private void EnableRunMetrics()
    {
        DisableRunMetrics();
        _metricsCombat = null;
        _metricsEnemies.Clear();
        CombatManager.Instance.CombatSetUp += TrackMetricsEnemies;
        CombatManager.Instance.CreaturesChanged += TrackMetricsEnemies;
    }

    private void DisableRunMetrics()
    {
        CombatManager.Instance.CombatSetUp -= TrackMetricsEnemies;
        CombatManager.Instance.CreaturesChanged -= TrackMetricsEnemies;
    }

    private void TrackMetricsEnemies(CombatState state)
    {
        if (!ReferenceEquals(_metricsCombat, state))
        {
            _metricsCombat = state;
            _metricsEnemies.Clear();
        }
        foreach (var enemy in state.Enemies)
            if (!_metricsEnemies.Contains(enemy)) _metricsEnemies.Add(enemy);
    }

    // Read the native post-action creatures, never the previous decision's HP.
    // Retained references also include killed enemies and all spawned enemies,
    // so killing an enemy cannot remove its max HP from the denominator.
    // This separate command leaves existing decision/checkpoint schemas intact.
    public Dictionary<string, object?> GetRunMetrics()
    {
        if (_runState == null) return Error("No run in progress");
        var player = _runState.Players[0];
        var combat = (_runState.CurrentRoom as CombatRoom)?.CombatState;
        if (combat != null) TrackMetricsEnemies(combat);
        var enemies = combat == null ? new List<Dictionary<string, object?>>() :
            _metricsEnemies.Select((enemy, index) => new Dictionary<string, object?>
            {
                ["roster_index"] = index,
                ["id"] = enemy.Monster?.Id.ToString(),
                ["name"] = _loc.Monster(enemy.Monster?.Id.Entry ?? "UNKNOWN"),
                ["hp"] = Math.Max(0, enemy.CurrentHp),
                ["max_hp"] = enemy.MaxHp,
                ["is_dead"] = enemy.IsDead,
            }).ToList();
        return new()
        {
            ["type"] = "run_metrics",
            ["source"] = "native_post_action",
            ["total_floor"] = _runState.TotalFloor,
            ["act"] = _runState.CurrentActIndex + 1,
            ["act_floor"] = _runState.ActFloor,
            ["round"] = combat?.RoundNumber,
            ["player_hp"] = player.Creature.IsDead ? 0 : player.Creature.CurrentHp,
            ["player_max_hp"] = player.Creature.MaxHp,
            ["enemy_hp_available"] = combat != null && enemies.Count > 0,
            ["enemies"] = enemies,
            ["enemy_hp"] = enemies.Sum(e => (int)e["hp"]!),
            ["enemy_max_hp"] = enemies.Sum(e => (int)e["max_hp"]!),
        };
    }
}
