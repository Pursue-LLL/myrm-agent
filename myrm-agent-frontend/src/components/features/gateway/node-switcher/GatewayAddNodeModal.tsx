/**
 * Gateway Add Node Modal Dialog
 * 登记新的 Agent 宿主网关节点模态对话框
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，具体强类型；
 * 2. 零原生 emoji，采用 Lucide 图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 语义标签与关联；
 * 5. 行数严格受控在 200 行以内。
 */

import React, { useState } from 'react';
import { X } from 'lucide-react';
import { GatewayNodeDescriptor } from './gatewayNodeTypes';

export interface GatewayAddNodeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddNode: (
    node: Omit<GatewayNodeDescriptor, 'id' | 'status' | 'pingMs' | 'lastCheckedAt'>
  ) => void;
}

export const GatewayAddNodeModal: React.FC<GatewayAddNodeModalProps> = ({
  isOpen,
  onClose,
  onAddNode,
}) => {
  const [formName, setFormName] = useState<string>('');
  const [formUrl, setFormUrl] = useState<string>('');
  const [formToken, setFormToken] = useState<string>('');
  const [formTag, setFormTag] = useState<string>('远程 VPS');

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    if (formName.trim().length === 0 || formUrl.trim().length === 0) {
      return;
    }

    onAddNode({
      name: formName.trim(),
      endpointUrl: formUrl.trim(),
      token: formToken.trim().length > 0 ? formToken.trim() : undefined,
      isDefault: false,
      tags: [formTag],
    });

    setFormName('');
    setFormUrl('');
    setFormToken('');
  };

  return (
    <dialog
      open
      data-testid="add-node-dialog"
      aria-label="添加新网关宿主节点"
      className="fixed inset-0 z-50 flex h-full w-full items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="flex w-full max-w-md flex-col rounded-xl border border-neutral-800 bg-neutral-900 p-5 text-neutral-100 shadow-2xl">
        <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
          <h4 className="text-sm font-semibold text-neutral-100">登记新的 Agent 宿主网关</h4>
          <button
            type="button"
            onClick={onClose}
            data-testid="close-add-modal-btn"
            className="rounded p-1 text-neutral-400 hover:text-neutral-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 text-xs">
          <div>
            <label htmlFor="node-name-input" className="block text-neutral-400 mb-1">
              宿主节点名称
            </label>
            <input
              id="node-name-input"
              type="text"
              required
              value={formName}
              onChange={(e) => {
                setFormName(e.target.value);
              }}
              placeholder="例如: 办公室 4090 工作站"
              className="w-full rounded border border-neutral-700 bg-neutral-800 p-2 text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="node-url-input" className="block text-neutral-400 mb-1">
              网关 API Endpoint 地址
            </label>
            <input
              id="node-url-input"
              type="text"
              required
              value={formUrl}
              onChange={(e) => {
                setFormUrl(e.target.value);
              }}
              placeholder="http://192.168.1.50:8000 或 https://vps.example.com"
              className="w-full rounded border border-neutral-700 bg-neutral-800 p-2 text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="node-token-input" className="block text-neutral-400 mb-1">
              访问凭证 / Bearer Token (可选)
            </label>
            <input
              id="node-token-input"
              type="password"
              value={formToken}
              onChange={(e) => {
                setFormToken(e.target.value);
              }}
              placeholder="留空则不附带授权头"
              className="w-full rounded border border-neutral-700 bg-neutral-800 p-2 text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="node-tag-select" className="block text-neutral-400 mb-1">
              所属环境分类
            </label>
            <select
              id="node-tag-select"
              value={formTag}
              onChange={(e) => {
                setFormTag(e.target.value);
              }}
              className="w-full rounded border border-neutral-700 bg-neutral-800 p-2 text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="本地">本地环境</option>
              <option value="GPU 算力">GPU 算力</option>
              <option value="NAS">NAS 私有云</option>
              <option value="远程 VPS">远程 VPS</option>
            </select>
          </div>

          <div className="mt-2 flex items-center justify-end gap-2 border-t border-neutral-800 pt-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-neutral-700 px-3 py-1.5 text-neutral-300 hover:bg-neutral-800"
            >
              取消
            </button>
            <button
              type="submit"
              data-testid="submit-add-node-btn"
              className="rounded bg-indigo-600 px-4 py-1.5 font-medium text-white hover:bg-indigo-500"
            >
              保存并开始探活
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
};
