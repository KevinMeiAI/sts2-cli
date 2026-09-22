using HarmonyLib;
using MegaCrit.Sts2.Core.Models.Monsters;
using MegaCrit.Sts2.Core.Nodes.Vfx.Backgrounds;

namespace Sts2Headless;

public partial class RunSimulator
{
    private static void PatchKaiserCrabCosmetics()
    {
        var harmony = new Harmony("sts2headless.kaisercrab");
        // Both arms normally find a shared Godot background in the combat scene.
        // Supply a scene-free node and skip only its animation methods. Keep the
        // monsters' native power setup, attacks, enrage and death logic intact.
        foreach (var type in new[] { typeof(Crusher), typeof(Rocket) })
        {
            harmony.Patch(AccessTools.PropertyGetter(type, "Background"),
                prefix: new HarmonyMethod(typeof(RunSimulator), nameof(CrabBackgroundPrefix)));
            // These two overrides contain only death SFX, animation and music.
            // Their direct NAudioManager singleton call is not null-safe.
            harmony.Patch(AccessTools.Method(type, "BeforeDeath"),
                prefix: new HarmonyMethod(typeof(RunSimulator), nameof(CrabAnimationTaskPrefix)));
        }
        foreach (var method in new[] { "PlayAttackAnim", "PlayRightSideChargeUpAnim", "PlayRightSideHeavy", "PlayRightRecharge" })
            harmony.Patch(AccessTools.Method(typeof(NKaiserCrabBossBackground), method),
                prefix: new HarmonyMethod(typeof(RunSimulator), nameof(CrabAnimationTaskPrefix)));
        foreach (var method in new[] { "PlayHurtAnim", "PlayArmDeathAnim", "PlayBodyDeathAnim" })
            harmony.Patch(AccessTools.Method(typeof(NKaiserCrabBossBackground), method),
                prefix: new HarmonyMethod(typeof(RunSimulator), nameof(CrabAnimationPrefix)));
    }

    private static bool CrabBackgroundPrefix(ref NKaiserCrabBossBackground __result)
    {
        __result = new NKaiserCrabBossBackground();
        return false;
    }

    private static bool CrabAnimationTaskPrefix(ref Task __result)
    {
        __result = Task.CompletedTask;
        return false;
    }

    private static bool CrabAnimationPrefix() => false;
}
