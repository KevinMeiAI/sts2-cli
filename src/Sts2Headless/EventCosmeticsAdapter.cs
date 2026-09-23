using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using HarmonyLib;
using MegaCrit.Sts2.Core.Audio.Debug;
using MegaCrit.Sts2.Core.Models.Events;

namespace Sts2Headless;

public partial class RunSimulator
{
    private static void PatchJungleMazeAudio(Harmony harmony)
    {
        var method = AccessTools.Method(typeof(JungleMazeAdventure), "SafetyInNumbers");
        var machine = method.GetCustomAttribute<AsyncStateMachineAttribute>()
            ?? throw new InvalidOperationException("JungleMazeAdventure.SafetyInNumbers state machine changed");
        harmony.Patch(AccessTools.Method(machine.StateMachineType, "MoveNext"),
            transpiler: new HarmonyMethod(typeof(RunSimulator), nameof(SkipJungleMazeAudio)));
    }

    private static IEnumerable<CodeInstruction> SkipJungleMazeAudio(IEnumerable<CodeInstruction> instructions)
    {
        var code = instructions.ToList();
        var play = AccessTools.Method(typeof(NDebugAudioManager), "Play",
            new[] { typeof(string), typeof(float), typeof(PitchVariance) });
        var calls = code.Where(i => i.Calls(play)).ToList();
        if (calls.Count != 1 || calls[0].opcode != OpCodes.Callvirt)
            throw new InvalidOperationException("JungleMazeAdventure audio call changed");
        // callvirt null-checks the absent audio singleton before a prefix on Play
        // could run. Replace only this call with a static wrapper, preserving its
        // stack shape, the native wait, GainGold, RNG and SetEventFinished calls.
        calls[0].opcode = OpCodes.Call;
        calls[0].operand = AccessTools.Method(typeof(RunSimulator), nameof(NoEventAudio));
        return code;
    }

    private static int NoEventAudio(NDebugAudioManager? audio, string path, float volume,
        PitchVariance variance) => 0;
}
