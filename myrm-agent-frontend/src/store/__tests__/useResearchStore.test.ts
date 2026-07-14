import { act } from '@testing-library/react';

import useResearchStore from '../useResearchStore';

describe('useResearchStore', () => {
  beforeEach(() => {
    act(() => {
      useResearchStore.getState().reset();
    });
  });

  describe('addResource', () => {
    it('adds a resource with selected=true', () => {
      act(() => {
        useResearchStore.getState().addResource({
          id: 'concept:ml',
          name: 'Machine Learning',
          type: 'concept',
        });
      });

      const { resources } = useResearchStore.getState();
      expect(resources).toHaveLength(1);
      expect(resources[0]).toMatchObject({
        id: 'concept:ml',
        name: 'Machine Learning',
        type: 'concept',
        selected: true,
      });
    });

    it('ignores duplicate resource by id', () => {
      act(() => {
        const { addResource } = useResearchStore.getState();
        addResource({ id: 'concept:ml', name: 'ML', type: 'concept' });
        addResource({ id: 'concept:ml', name: 'ML Duplicate', type: 'concept' });
      });

      expect(useResearchStore.getState().resources).toHaveLength(1);
      expect(useResearchStore.getState().resources[0].name).toBe('ML');
    });
  });

  describe('removeResource', () => {
    it('removes a resource by id', () => {
      act(() => {
        const { addResource } = useResearchStore.getState();
        addResource({ id: 'concept:a', name: 'A', type: 'concept' });
        addResource({ id: 'concept:b', name: 'B', type: 'concept' });
      });
      act(() => {
        useResearchStore.getState().removeResource('concept:a');
      });

      const { resources } = useResearchStore.getState();
      expect(resources).toHaveLength(1);
      expect(resources[0].id).toBe('concept:b');
    });
  });

  describe('toggleResource', () => {
    it('toggles selected state', () => {
      act(() => {
        useResearchStore.getState().addResource({ id: 'r1', name: 'R1', type: 'raw_file' });
      });
      expect(useResearchStore.getState().resources[0].selected).toBe(true);

      act(() => {
        useResearchStore.getState().toggleResource('r1');
      });
      expect(useResearchStore.getState().resources[0].selected).toBe(false);

      act(() => {
        useResearchStore.getState().toggleResource('r1');
      });
      expect(useResearchStore.getState().resources[0].selected).toBe(true);
    });

    it('does nothing for nonexistent id', () => {
      act(() => {
        useResearchStore.getState().addResource({ id: 'r1', name: 'R1', type: 'raw_file' });
        useResearchStore.getState().toggleResource('nonexistent');
      });
      expect(useResearchStore.getState().resources).toHaveLength(1);
    });
  });

  describe('selectAll / deselectAll', () => {
    it('selects all resources', () => {
      act(() => {
        const { addResource, toggleResource } = useResearchStore.getState();
        addResource({ id: 'a', name: 'A', type: 'concept' });
        addResource({ id: 'b', name: 'B', type: 'raw_file' });
        toggleResource('a');
      });

      act(() => {
        useResearchStore.getState().selectAll();
      });

      expect(useResearchStore.getState().resources.every((r) => r.selected)).toBe(true);
    });

    it('deselects all resources', () => {
      act(() => {
        const { addResource } = useResearchStore.getState();
        addResource({ id: 'a', name: 'A', type: 'concept' });
        addResource({ id: 'b', name: 'B', type: 'raw_file' });
      });

      act(() => {
        useResearchStore.getState().deselectAll();
      });

      expect(useResearchStore.getState().resources.every((r) => !r.selected)).toBe(true);
    });
  });

  describe('setActiveTab', () => {
    it('switches active tab', () => {
      expect(useResearchStore.getState().activeTab).toBe('resources');

      act(() => {
        useResearchStore.getState().setActiveTab('chat');
      });
      expect(useResearchStore.getState().activeTab).toBe('chat');

      act(() => {
        useResearchStore.getState().setActiveTab('output');
      });
      expect(useResearchStore.getState().activeTab).toBe('output');
    });
  });

  describe('getSelectedResources', () => {
    it('returns only selected resources', () => {
      act(() => {
        const { addResource, toggleResource } = useResearchStore.getState();
        addResource({ id: 'a', name: 'A', type: 'concept' });
        addResource({ id: 'b', name: 'B', type: 'raw_file' });
        addResource({ id: 'c', name: 'C', type: 'concept' });
        toggleResource('b');
      });

      const selected = useResearchStore.getState().getSelectedResources();
      expect(selected).toHaveLength(2);
      expect(selected.map((r) => r.id)).toEqual(['a', 'c']);
    });
  });

  describe('reset', () => {
    it('restores initial state', () => {
      act(() => {
        const { addResource, setActiveTab } = useResearchStore.getState();
        addResource({ id: 'a', name: 'A', type: 'concept' });
        setActiveTab('output');
      });

      act(() => {
        useResearchStore.getState().reset();
      });

      const state = useResearchStore.getState();
      expect(state.resources).toHaveLength(0);
      expect(state.activeTab).toBe('resources');
    });
  });
});
