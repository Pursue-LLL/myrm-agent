/**
 * [INPUT]
 * - Internal widget modules: types, store, bridge, container, generator
 *
 * [OUTPUT]
 * - Public exports for Embeddable Agent Widget & Host Context Bridge
 *
 * [POS]
 * Facade entry point for widget feature (Item 41 P1).
 */

export * from "./widgetTypes";
export * from "./useWidgetBridgeStore";
export * from "./HostContextBridge";
export * from "./EmbeddableWidgetContainer";
export * from "./WidgetGeneratorModal";
