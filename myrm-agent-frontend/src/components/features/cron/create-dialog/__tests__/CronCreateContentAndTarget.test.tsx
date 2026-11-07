// @vitest-environment jsdom
import { cleanup, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  apiRequest,
  choose,
  click,
  combo,
  fetchAgents,
  fetchWorkflowTemplates,
  listChannelStatuses,
  openCustom,
  openSelect,
  placeholder,
  radio,
  resetKit,
  state,
  templateOf,
  typeInto,
} from './createDialogTestKit';

beforeEach(resetKit);
afterEach(cleanup);

describe('job type and content', () => {
  it('offers agent, shell, script and reminder jobs on a local deployment', async () => {
    await openCustom();

    for (const name of ['jobTypeAgent', 'jobTypeShell', 'jobTypeScript', 'jobTypeReminder']) {
      expect(radio(name)).toBeInTheDocument();
    }
    expect(radio('jobTypeAgent')).toHaveAttribute('aria-checked', 'true');
  });

  it('has no shell jobs on a sandbox deployment', async () => {
    apiRequest.mockResolvedValue({ deploy_mode: 'sandbox' });
    await openCustom();

    expect(screen.queryByRole('radio', { name: 'jobTypeShell' })).toBeNull();
    expect(radio('jobTypeScript')).toBeInTheDocument();
  });

  it('has no shell jobs while the deployment mode is still being looked up', async () => {
    apiRequest.mockReturnValue(new Promise(() => undefined));
    await openCustom();

    expect(screen.queryByRole('radio', { name: 'jobTypeShell' })).toBeNull();
  });

  it('has no shell jobs when the deployment mode cannot be read', async () => {
    apiRequest.mockRejectedValue(new Error('offline'));
    await openCustom();

    expect(screen.queryByRole('radio', { name: 'jobTypeShell' })).toBeNull();
  });

  it('refreshes the agent list and the connected channels when it opens', async () => {
    await openCustom();

    expect(fetchAgents).toHaveBeenCalledTimes(1);
    expect(listChannelStatuses).toHaveBeenCalledTimes(1);
    expect(apiRequest).toHaveBeenCalledWith('/health/info');
  });

  it('asks for a prompt and a workflow template for an agent job', async () => {
    await openCustom();

    expect(placeholder('createPromptPlaceholder')).toBeInTheDocument();
    expect(screen.getByText('createWorkflowTemplateLabel')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('createCommandPlaceholder')).toBeNull();
  });

  it('asks for a reminder text with its hint, and no workflow template', async () => {
    await openCustom();
    await click(radio('jobTypeReminder'));

    expect(placeholder('createReminderPlaceholder')).toBeInTheDocument();
    expect(screen.getByText('createReminderHint')).toBeInTheDocument();
    expect(screen.queryByText('createWorkflowTemplateLabel')).toBeNull();
    expect(screen.queryByPlaceholderText('createPromptPlaceholder')).toBeNull();
  });

  it('asks for a command for a shell job', async () => {
    await openCustom();
    await click(radio('jobTypeShell'));

    expect(placeholder('createCommandPlaceholder')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('createPromptPlaceholder')).toBeNull();
  });

  it('asks for a script and explains it for a script job', async () => {
    await openCustom();
    await click(radio('jobTypeScript'));

    expect(placeholder('scriptPlaceholder')).toBeInTheDocument();
    expect(screen.getByText('scriptHint')).toBeInTheDocument();
  });

  it('keeps the text typed for a kind while the user looks at another one', async () => {
    await openCustom();
    await typeInto(placeholder('createPromptPlaceholder'), 'Summarise the news');
    await click(radio('jobTypeShell'));
    await typeInto(placeholder('createCommandPlaceholder'), 'ls');
    await click(radio('jobTypeAgent'));

    expect(placeholder('createPromptPlaceholder')).toHaveValue('Summarise the news');
    await click(radio('jobTypeShell'));
    expect(placeholder('createCommandPlaceholder')).toHaveValue('ls');
  });

  it('keeps the name field for every kind', async () => {
    await openCustom();
    await typeInto(placeholder('createNamePlaceholder'), 'Morning brief');
    await click(radio('jobTypeScript'));

    expect(placeholder('createNamePlaceholder')).toHaveValue('Morning brief');
  });
});

describe('workflow templates', () => {
  it('lists the trusted templates after the no-template choice and hides the untrusted ones', async () => {
    fetchWorkflowTemplates.mockResolvedValue({
      templates: [templateOf('t1', 'Daily digest'), templateOf('t2', 'Draft only', [], false)],
    });
    await openCustom();

    await openSelect(combo('createWorkflowTemplateNone'));
    const options = screen.getAllByRole('option').map((option) => option.textContent);

    expect(options).toEqual(['createWorkflowTemplateNone', 'Daily digest']);
  });

  it('offers only the no-template choice when the templates cannot be loaded', async () => {
    fetchWorkflowTemplates.mockRejectedValue(new Error('offline'));
    await openCustom();

    await openSelect(combo('createWorkflowTemplateNone'));

    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['createWorkflowTemplateNone']);
  });

  it('shows the chosen template in the select', async () => {
    fetchWorkflowTemplates.mockResolvedValue({ templates: [templateOf('t1', 'Daily digest')] });
    await openCustom();

    await choose(combo('createWorkflowTemplateNone'), 'Daily digest');

    expect(combo('Daily digest')).toBeInTheDocument();
  });
});

describe('delivery channel', () => {
  const running = (name: string) => ({ name, status: 'running' });

  it('offers no delivery choice without a connected channel', async () => {
    await openCustom();

    expect(screen.queryByText('deliveryLabel')).toBeNull();
  });

  it('offers no delivery choice when the channels cannot be listed', async () => {
    listChannelStatuses.mockRejectedValue(new Error('offline'));
    await openCustom();

    expect(screen.queryByText('deliveryLabel')).toBeNull();
  });

  it('offers chat and the running IM channels, not stopped or built-in ones', async () => {
    listChannelStatuses.mockResolvedValue([
      running('telegram'),
      running('slack'),
      { name: 'discord', status: 'stopped' },
      running('web'),
      running('webhook'),
    ]);
    await openCustom();

    const group = screen.getByText('deliveryLabel').parentElement as HTMLElement;
    expect(
      within(group)
        .getAllByRole('radio')
        .map((item) => item.textContent),
    ).toEqual(['deliveryChat', 'Telegram', 'Slack']);
    expect(radio('deliveryChat')).toHaveAttribute('aria-checked', 'true');
  });

  it('asks for a recipient with an example only for an IM channel', async () => {
    listChannelStatuses.mockResolvedValue([running('telegram')]);
    await openCustom();
    const textInputs = () => screen.getAllByRole('textbox').length;
    const withoutRecipient = textInputs();
    expect(screen.queryByPlaceholderText('123456789')).toBeNull();

    await click(radio('Telegram'));
    expect(textInputs()).toBe(withoutRecipient + 1);
    await typeInto(placeholder('123456789'), '42');
    expect(placeholder('123456789')).toHaveValue('42');

    await click(radio('deliveryChat'));
    expect(textInputs()).toBe(withoutRecipient);
  });
});

describe('agent binding', () => {
  const agents = [
    { id: 'a1', name: 'Alpha' },
    { id: 'a2', name: 'Beta' },
  ];

  it('is not offered without agents', async () => {
    await openCustom();

    expect(screen.queryByText('createAgentLabel')).toBeNull();
  });

  it('lists the default agent and the user agents for an agent job', async () => {
    state.agents = agents;
    await openCustom();

    await openSelect(combo('createAgentDefault'));

    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'createAgentDefault',
      'Alpha',
      'Beta',
    ]);
  });

  it('shows the chosen agent', async () => {
    state.agents = agents;
    await openCustom();

    await choose(combo('createAgentDefault'), 'Beta');

    expect(combo('Beta')).toBeInTheDocument();
  });

  it('is not offered for the other kinds of job', async () => {
    state.agents = agents;
    await openCustom();
    await click(radio('jobTypeReminder'));

    expect(screen.queryByText('createAgentLabel')).toBeNull();
  });
});
