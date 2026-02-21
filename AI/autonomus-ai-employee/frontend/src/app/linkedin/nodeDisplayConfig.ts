/**
 * Display configuration for LinkedIn pipeline nodes.
 * Maps backend node names to user-friendly labels, icons, and colors.
 */

export interface NodeDisplayConfig {
  icon: string;
  label: string;
  color: string;
  description: string;
}

export const NODE_DISPLAY: Record<string, NodeDisplayConfig> = {
  input_node: {
    icon: "📋",
    label: "Validating Input",
    color: "blue",
    description: "Parsing and validating your topic and requirements",
  },
  input_refinement: {
    icon: "✨",
    label: "Refining Topic",
    color: "purple",
    description: "Clarifying and enhancing the topic for better results",
  },
  style_memory_fetch: {
    icon: "🎨",
    label: "Loading Your Style",
    color: "pink",
    description: "Fetching your past posts to match your writing style",
  },
  viral_posts_fetch: {
    icon: "🔥",
    label: "Analyzing Viral Posts",
    color: "orange",
    description: "Loading high-performing post templates and patterns",
  },
  trend_discovery: {
    icon: "📊",
    label: "Discovering Trends",
    color: "blue",
    description: "Researching current trends and conversations around your topic",
  },
  claim_extraction: {
    icon: "💡",
    label: "Extracting Claims",
    color: "yellow",
    description: "Identifying key facts and claims from research",
  },
  fact_verification: {
    icon: "🔍",
    label: "Verifying Facts",
    color: "green",
    description: "Fact-checking claims against authoritative sources",
  },
  research_quality: {
    icon: "📈",
    label: "Evaluating Research",
    color: "blue",
    description: "Assessing research quality and confidence score",
  },
  source_query_generator: {
    icon: "🎯",
    label: "Planning Targeted Research",
    color: "purple",
    description: "Generating source-specific queries for deeper research",
  },
  targeted_research: {
    icon: "🔬",
    label: "Conducting Targeted Research",
    color: "indigo",
    description: "Executing focused searches for authoritative sources",
  },
  contradiction: {
    icon: "⚠️",
    label: "Finding Contradictions",
    color: "orange",
    description: "Searching for counter-claims and potential controversies",
  },
  angle_builder: {
    icon: "🎯",
    label: "Building Angle",
    color: "purple",
    description: "Choosing the most impactful strategic angle",
  },
  pov_builder: {
    icon: "👤",
    label: "Framing POV",
    color: "blue",
    description: "Crafting insider perspective for authority positioning",
  },
  hook_generator: {
    icon: "🪝",
    label: "Generating Hooks",
    color: "pink",
    description: "Creating multiple attention-grabbing opening hooks",
  },
  post_writer: {
    icon: "✍️",
    label: "Writing Post",
    color: "green",
    description: "Composing the full LinkedIn post content",
  },
  engagement_optimizer: {
    icon: "🚀",
    label: "Optimizing Engagement",
    color: "blue",
    description: "Refining the post for maximum engagement potential",
  },
  viral_scorer: {
    icon: "📊",
    label: "Scoring Virality",
    color: "purple",
    description: "Calculating viral potential and realism scores",
  },
  store_post: {
    icon: "💾",
    label: "Saving Draft",
    color: "gray",
    description: "Storing post to database",
  },
  human_approval: {
    icon: "👁️",
    label: "Awaiting Approval",
    color: "yellow",
    description: "Waiting for your review and approval",
  },
  linkedin_publish: {
    icon: "📤",
    label: "Publishing to LinkedIn",
    color: "blue",
    description: "Publishing your approved post to LinkedIn",
  },
};

/**
 * Get display config for a node, with fallback for unknown nodes
 */
export function getNodeDisplay(nodeName: string | undefined): NodeDisplayConfig {
  if (!nodeName) {
    return {
      icon: "⏳",
      label: "Processing",
      color: "gray",
      description: "Pipeline in progress",
    };
  }

  return (
    NODE_DISPLAY[nodeName] || {
      icon: "⚙️",
      label: nodeName
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" "),
      color: "gray",
      description: `Executing ${nodeName}`,
    }
  );
}

/**
 * Map event type to display status
 */
export function getEventStatus(eventType: string): string {
  switch (eventType) {
    case "node_start":
      return "running";
    case "node_complete":
      return "complete";
    case "error":
      return "error";
    case "pipeline_start":
      return "starting";
    case "pipeline_complete":
      return "done";
    default:
      return "active";
  }
}
