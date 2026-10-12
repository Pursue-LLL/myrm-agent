/**
 * [INPUT]
 * - ExtensionUIModal from ./ExtensionUIModal
 * - extensionUITypes from ./extensionUITypes
 *
 * [OUTPUT]
 * - ExtensionUIModal, UIRequestItem, UISelectOption, UIRequestType, UIResponsePayload
 *
 * [POS]
 * Module facade for Transport-Agnostic Extension UI feature (Item 28).
 */

export { ExtensionUIModal } from './ExtensionUIModal';
export type {
  UIRequestItem,
  UISelectOption,
  UIRequestType,
  UIResponsePayload,
} from './extensionUITypes';
