/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MobileVoiceStagedInput } from '../MobileVoiceStagedInput';

const mockToggleRecognition = vi.fn();
const mockResetTranscript = vi.fn();
const mockStopRecognition = vi.fn();
let mockIsListening = false;
let mockTranscript = '';

vi.mock('../useVoiceRecognition', () => ({
  useVoiceRecognition: (options?: { onTranscriptChunk?: (t: string) => void; onUnsupported?: () => void }) => {
    if (mockTranscript && options?.onTranscriptChunk) {
      options.onTranscriptChunk(mockTranscript);
    }
    return {
      isListening: mockIsListening,
      transcript: mockTranscript,
      toggleRecognition: mockToggleRecognition,
      resetTranscript: mockResetTranscript,
      stopRecognition: mockStopRecognition,
    };
  },
}));

describe('MobileVoiceStagedInput Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsListening = false;
    mockTranscript = '';
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <MobileVoiceStagedInput
        isOpen={false}
        onClose={vi.fn()}
        onSend={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders correctly when isOpen is true', () => {
    render(
      <MobileVoiceStagedInput
        isOpen={true}
        onClose={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByPlaceholderText(/placeholder|语音/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /send|发送/i })).toBeDefined();
  });

  it('toggles voice recognition when microphone button is clicked', () => {
    render(
      <MobileVoiceStagedInput
        isOpen={true}
        onClose={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    const micBtn = screen.getByRole('button', { name: /tapToSpeak|倾听|speak/i });
    fireEvent.click(micBtn);
    expect(mockToggleRecognition).toHaveBeenCalledTimes(1);
  });

  it('allows manual text editing and sends trimmed text', () => {
    const onSendMock = vi.fn();
    const onCloseMock = vi.fn();

    render(
      <MobileVoiceStagedInput
        isOpen={true}
        onClose={onCloseMock}
        onSend={onSendMock}
      />,
    );

    const textarea = screen.getByPlaceholderText(/placeholder|语音/i);
    fireEvent.change(textarea, { target: { value: '请帮我优化代码性能并在手机端复盘' } });

    const sendBtn = screen.getByRole('button', { name: /send|发送/i });
    fireEvent.click(sendBtn);

    expect(onSendMock).toHaveBeenCalledWith('请帮我优化代码性能并在手机端复盘');
    expect(mockStopRecognition).toHaveBeenCalled();
    expect(onCloseMock).toHaveBeenCalled();
  });

  it('clears text and resets transcript when clear button is clicked', () => {
    render(
      <MobileVoiceStagedInput
        isOpen={true}
        onClose={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    const textarea = screen.getByPlaceholderText(/placeholder|语音/i);
    fireEvent.change(textarea, { target: { value: '需要清空的草稿文本' } });

    const clearBtn = screen.getByRole('button', { name: /clear|清空/i });
    fireEvent.click(clearBtn);

    expect(mockResetTranscript).toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toBe('');
  });

  it('stops recognition and closes when dismiss button is clicked', () => {
    const onCloseMock = vi.fn();

    render(
      <MobileVoiceStagedInput
        isOpen={true}
        onClose={onCloseMock}
        onSend={vi.fn()}
      />,
    );

    const dismissBtn = screen.getByRole('button', { name: /cancel|收起/i });
    fireEvent.click(dismissBtn);

    expect(mockStopRecognition).toHaveBeenCalled();
    expect(onCloseMock).toHaveBeenCalled();
  });
});
