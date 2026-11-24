"""LangGraph construction for the PhishWalk ReAct loop."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.graph.nodes.act import act_node
from agent.graph.nodes.decision import decision_node
from agent.graph.nodes.finalize import finalize_node
from agent.graph.nodes.observe import observe_node
from agent.graph.nodes.one_shot import one_shot_decision_node
from agent.graph.routing import (
    route_after_act,
    route_after_decision,
    route_after_one_shot_decision,
)
from agent.graph.runtime import PhishWalkRuntime
from agent.graph.state import PhishWalkState


def build_phishwalk_graph() -> CompiledStateGraph:
    """Build the minimal observe-decide-act PhishWalk graph."""
    graph_builder = StateGraph(
        state_schema=PhishWalkState,
        context_schema=PhishWalkRuntime,
    )

    graph_builder.add_node("observe", observe_node)
    graph_builder.add_node("decision", decision_node)
    graph_builder.add_node("act", act_node)
    graph_builder.add_node("final_observe", observe_node)
    graph_builder.add_node("finalize", finalize_node)

    graph_builder.add_edge(START, "observe")
    graph_builder.add_edge("observe", "decision")
    graph_builder.add_conditional_edges(
        "decision",
        route_after_decision,
        {
            "act": "act",
            "decision": "decision",
            "final_observe": "final_observe",
        },
    )
    graph_builder.add_conditional_edges(
        "act",
        route_after_act,
        {
            "observe": "observe",
            "final_observe": "final_observe",
            "end": END,
        },
    )
    graph_builder.add_edge("final_observe", "finalize")
    graph_builder.add_edge("finalize", END)

    return graph_builder.compile()


def build_one_shot_graph() -> CompiledStateGraph:
    """Build an observe-once graph that never exposes browser actions."""
    graph_builder = StateGraph(
        state_schema=PhishWalkState,
        context_schema=PhishWalkRuntime,
    )
    graph_builder.add_node("observe", observe_node)
    graph_builder.add_node("one_shot_decision", one_shot_decision_node)
    graph_builder.add_edge(START, "observe")
    graph_builder.add_edge("observe", "one_shot_decision")
    graph_builder.add_conditional_edges(
        "one_shot_decision",
        route_after_one_shot_decision,
        {
            "one_shot_decision": "one_shot_decision",
            "end": END,
        },
    )
    return graph_builder.compile()
