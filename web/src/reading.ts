export type CodeReading = {
  topic: string;
  plain: string;
};

const TOPICS: { pattern: RegExp; topic: string; plain: string }[] = [
  {
    pattern: /roach|rodent|mouse|mice|\brats?\b|vermin|pest|fruit fly|\bflies\b|insects?|harborage/i,
    topic: "Pests",
    plain: "This rule is about pests. It covers insects or rodents on the premises, and conditions that let them in.",
  },
  {
    pattern: /hand\s?wash|handwashing|hands? (?:not |were not )?clean|soap|hand sink/i,
    topic: "Handwashing",
    plain: "This rule is about washing hands. Hands that stay dirty after contamination can carry germs onto food.",
  },
  {
    pattern: /bare hand|\bgloves?\b/i,
    topic: "Hands on food",
    plain: "This rule is about bare hands or gloves on food. Ready-to-eat food is supposed to stay off unclean hands.",
  },
  {
    pattern: /hot hold|hot food|135\s*°?\s*f|140\s*°?\s*f|held at or above/i,
    topic: "Hot food",
    plain: "This rule is about keeping hot food hot. Food that cools into the danger zone can let bacteria multiply.",
  },
  {
    pattern: /cold hold|refrigerat|41\s*°?\s*f|38\s*°?\s*f|held above|not held at or below/i,
    topic: "Cold food",
    plain: "This rule is about keeping cold food cold. Food that warms into the danger zone can let bacteria multiply.",
  },
  {
    pattern: /not cooled|cooling|reheat/i,
    topic: "Cooling and reheating",
    plain: "This rule is about how fast food is cooled or reheated. A long stay in the danger zone can let bacteria multiply.",
  },
  {
    pattern: /cook(?:ed|ing)?\b|internal temperature|undercook/i,
    topic: "Cooking",
    plain: "This rule is about cooking temperature. Food that is not cooked through can still carry pathogens.",
  },
  {
    pattern: /thermometer/i,
    topic: "Thermometer",
    plain: "This rule is about having a working thermometer, so staff can check that food is hot or cold enough.",
  },
  {
    pattern: /cross-?contamin|raw, cooked|raw or cooked|separate raw/i,
    topic: "Cross-contamination",
    plain: "This rule is about keeping raw food away from food that is ready to eat, so juices and germs do not spread.",
  },
  {
    pattern: /food and non-food contact/i,
    topic: "Clean surfaces",
    plain: "This rule is about keeping utensils and equipment clean, including pieces that touch food and pieces that do not.",
  },
  {
    pattern: /non-food contact/i,
    topic: "Equipment",
    plain: "This rule is about equipment that does not touch food directly: what it is made of, whether it is clean, and whether staff can clean around it.",
  },
  {
    pattern: /saniti[sz]|ware ?wash|food contact|wiping cloth|utensil/i,
    topic: "Clean surfaces",
    plain: "This rule is about washing and sanitizing surfaces or tools that touch food.",
  },
  {
    pattern: /refillable|returnable/i,
    topic: "Refillable containers",
    plain: "This rule is about customer containers that are refilled. The department wants a written procedure so those containers do not contaminate the food.",
  },
  {
    pattern: /not protected|protected from/i,
    topic: "Food protection",
    plain: "This rule is about keeping food covered and away from things that could contaminate it during storage, preparation, or service.",
  },
  {
    pattern: /walls|ceilings|floors/i,
    topic: "Floors and walls",
    plain: "This rule is about floors, walls, or ceilings: whether they are built as required, in good repair, and clean.",
  },
  {
    pattern: /food handler/i,
    topic: "Food handlers",
    plain: "This rule is about the people handling food, including the training or hygiene the city requires of them.",
  },
  {
    pattern: /lighting|foot-candles/i,
    topic: "Lighting",
    plain: "This rule is about enough light in the kitchen, and light fixtures that are shielded so broken glass cannot fall into food.",
  },
  {
    pattern: /ventilation/i,
    topic: "Ventilation",
    plain: "This rule is about venting rooms and equipment so heat, steam, and fumes do not build up.",
  },
  {
    pattern: /litter|unnecessary articles|premises maintained/i,
    topic: "Premises",
    plain: "This rule is about keeping the premises free of litter and storing cleaning equipment so it does not contaminate food.",
  },
  {
    pattern: /original container|properly labeled|customer advisory/i,
    topic: "Labeling",
    plain: "This rule is about food kept in labeled containers, and posted warnings when customers need them.",
  },
  {
    pattern: /date mark|expired|shelf life|seven day|held past/i,
    topic: "Date and discard",
    plain: "This rule is about how long prepared food may be kept, and when it has to be thrown out.",
  },
  {
    pattern: /thaw|defrost/i,
    topic: "Thawing",
    plain: "This rule is about thawing food in a safe way, instead of leaving it where bacteria can grow.",
  },
  {
    pattern: /adulterat|spoil|contaminat|unapproved source|approved source|dented|swollen/i,
    topic: "Food condition",
    plain: "This rule is about food that is contaminated, spoiled, or from a source the department does not accept.",
  },
  {
    pattern: /toxic|chemical|poison|pesticide|sanitizer stored/i,
    topic: "Chemicals",
    plain: "This rule is about storing cleaners and other chemicals so they cannot get into food.",
  },
  {
    pattern: /plumb|sewage|drain|backflow|grease trap|waste ?water/i,
    topic: "Plumbing",
    plain: "This rule is about drains, sewage, and backflow. A plumbing failure can contaminate the kitchen.",
  },
  {
    pattern: /toilet|restroom|bathroom|hand washing facility/i,
    topic: "Restroom",
    plain: "This rule is about the restroom or its sink: supplies, cleanliness, or whether staff can wash.",
  },
  {
    pattern: /food protection certificate|person in charge|certified food|supervisor of food|food service manager/i,
    topic: "Supervision",
    plain: "This rule is about who is in charge during food handling, and whether that person holds the required certificate.",
  },
  {
    pattern: /\bill\b|sick|symptom|discharge|lesion|wound/i,
    topic: "Illness",
    plain: "This rule is about keeping people with symptoms that spread disease away from food.",
  },
  {
    pattern: /hair|jewelry|personal cleanliness|eating|drinking|tobacco|smoking/i,
    topic: "Hygiene",
    plain: "This rule is about personal cleanliness in the kitchen: hair, clothing, jewelry, or eating and drinking over food.",
  },
  {
    pattern: /garbage|refuse|rubbish|waste receptacle/i,
    topic: "Garbage",
    plain: "This rule is about garbage storage. Open or overflowing waste attracts pests and contaminates the area.",
  },
  {
    pattern: /permit|registration|license/i,
    topic: "Permit",
    plain: "This rule is about having a current permit or other authorization to operate.",
  },
];

export function readCode(description: string | null): CodeReading {
  if (!description) {
    return {
      topic: "Unlisted code",
      plain: "No description is on the record, so only the code is shown.",
    };
  }
  const match = TOPICS.find((topic) => topic.pattern.test(description));
  if (!match) {
    return {
      topic: "Cited rule",
      plain: "This is a cited rule. The wording is below.",
    };
  }
  return { topic: match.topic, plain: match.plain };
}

export function scaleCaption(cityId: string): string | null {
  switch (cityId) {
    case "new_york":
      return "A is 0–13. B is 14–27. C is 28 or more. A lower score is cleaner.";
    case "los_angeles":
      return "A is 90–100. B is 80–89. C is 70–79. A higher score is cleaner.";
    case "austin":
      return "Scores run from 0 to 100. 90 or above is the cleaner result. A higher score is cleaner.";
    case "king_county":
      return "Grades run Excellent, Good, Okay, then Needs To Improve. A lower score is cleaner.";
    case "chicago":
      return "Results run Pass, Pass with conditions, then Fail.";
    case "boston":
      return "Pass is the cleaner result. Fail is the worse result.";
    case "san_francisco":
      return "Results run Pass, Conditional Pass, then Closure.";
    default:
      return null;
  }
}

export function statusSentence(cityId: string, serious: boolean | null): string | null {
  if (serious == null) return null;
  const lines: Record<string, [string, string]> = {
    new_york: [
      "The last inspection included a critical violation.",
      "The last inspection had no critical violation.",
    ],
    chicago: ["The last inspection result was Fail.", "The last inspection result was not Fail."],
    king_county: [
      "The last inspection included a serious violation.",
      "The last inspection had no serious violation.",
    ],
    los_angeles: [
      "The last inspection included a serious violation.",
      "The last inspection had no serious violation.",
    ],
    boston: ["The last inspection result was a fail.", "The last inspection result was not a fail."],
    san_francisco: [
      "The last inspection was a conditional pass or a closure.",
      "The last inspection was a pass.",
    ],
    austin: ["The last routine score was below 90.", "The last routine score was 90 or above."],
  };
  const pair = lines[cityId];
  if (!pair) return null;
  return serious ? pair[0] : pair[1];
}

const COUNT_WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
];

export function inspectionAge(isoDate: string | null, today = new Date()): string | null {
  const inspected = parseInspectionDate(isoDate);
  if (!inspected) return null;
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.round((startToday.getTime() - inspected.getTime()) / 86_400_000);
  if (days < 0) return null;
  if (days === 0) return "Inspected today.";
  if (days === 1) return "Inspected yesterday.";
  if (days < 7) return `Inspected ${days} days ago.`;
  if (days < 30) return `Inspected ${span(Math.floor(days / 7), "week")} ago.`;
  if (days < 365) {
    const months = Math.max(1, Math.round(days / 30.44));
    if (months >= 12) return "Inspected one year ago.";
    return `Inspected ${span(months, "month")} ago.`;
  }
  return `Inspected ${span(Math.max(1, Math.round(days / 365.25)), "year")} ago.`;
}

export function inspectionDateLabel(isoDate: string | null): string | null {
  const inspected = parseInspectionDate(isoDate);
  if (!inspected) return null;
  return inspected.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

export function trendSentence(
  trend: string | null | undefined,
  recentVisits: number,
  recentSerious: number,
): string | null {
  if (trend !== "cleaner" && trend !== "worse" && trend !== "steady") return null;
  if (recentVisits < 2) return null;
  const count = COUNT_WORDS[recentVisits] ?? String(recentVisits);
  const lead = `The last ${count} inspections`;
  if (trend === "cleaner") return `${lead} are getting cleaner.`;
  if (trend === "worse") return `${lead} are getting worse.`;
  if (recentSerious === 0) return `${lead} have stayed clean.`;
  if (recentSerious === recentVisits) return `${lead} have kept finding a serious problem.`;
  return `${lead} have stayed about the same.`;
}

export function scoreTrendSentence(scoreTrend: string | null | undefined): string | null {
  if (scoreTrend === "falling") return "Recent scores are falling.";
  if (scoreTrend === "rising") return "Recent scores are rising.";
  if (scoreTrend === "steady") return "Recent scores have stayed about the same.";
  return null;
}

export function peerSentence(
  cuisine: string | null | undefined,
  area: string | null | undefined,
  grade: string | null | undefined,
  peerCount: number,
  peerGradedCount: number,
  standing: string | null | undefined,
): string | null {
  if (!cuisine || !area || peerCount < 1) return null;
  const place = area === "Bronx" ? "the Bronx" : area;
  if (peerCount === 1) return `This is the only ${cuisine} restaurant on file in ${place}.`;
  const restaurants = `${peerCount} ${cuisine} restaurants`;
  if (standing === "better" || standing === "worse" || standing === "typical") {
    const group = peerGradedCount === peerCount ? restaurants : `${peerGradedCount} graded ${cuisine} restaurants`;
    const how = standing === "better" ? "better than most" : standing === "worse" ? "worse than most" : "typical";
    return `Among ${group} in ${place}, this ${grade ?? "grade"} is ${how}.`;
  }
  return `There are ${restaurants} on file in ${place}.`;
}

function parseInspectionDate(isoDate: string | null): Date | null {
  if (!isoDate) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return null;
  const inspected = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(inspected.getTime()) ? null : inspected;
}

function span(count: number, unit: string): string {
  const word = COUNT_WORDS[count] ?? String(count);
  return `${word} ${unit}${count === 1 ? "" : "s"}`;
}

export function codeIntro(cityId: string): string | null {
  if (cityId === "austin") return null;
  return "Each code is listed once, from the newest inspection that used it. The topic is a short reading of that rule.";
}

