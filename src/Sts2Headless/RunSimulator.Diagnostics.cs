using MegaCrit.Sts2.Core.Models;

namespace Sts2Headless;

public partial class RunSimulator
{
    /// <summary>Native event pools for offline coverage; never exposed to arena contestants.</summary>
    public Dictionary<string, object?> ListEvents()
    {
        EnsureModelDbInitialized();
        var events = ModelDb.AllEvents.Concat(ModelDb.AllAncients).Distinct()
            .OrderBy(e => e.Id.Entry).Select(e => new Dictionary<string, object?>
            {
                ["id"] = e.Id.Entry,
                ["model_type"] = e.GetType().Name,
                ["ancient"] = e is AncientEventModel,
            }).ToList();
        return new() { ["type"] = "event_catalog", ["events"] = events };
    }
}
