import { beforeEach, describe, expect, it } from 'vitest';
import {
  BASE_MODEL,
  VIDEO_MODEL,
  VISION_MODEL,
  configureModels,
  kit,
  makeFile,
  pickFiles,
  renderAttach,
  resetAttachKit,
} from './attachButtonKit';

beforeEach(resetAttachKit);

describe('AttachButton warning that the models cannot see images', () => {
  it('warns once for a pick with images, and still uploads them', async () => {
    configureModels({});
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.png'), makeFile('b.JPG'));

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('image');
    expect(view.list.current.map((file) => file.fileName)).toEqual(['a.png', 'b.JPG']);
  });

  it.each([
    ['the base model sees images', { vision: [BASE_MODEL] }],
    ['a vision fallback model is set that sees images', { visionFallback: VISION_MODEL, vision: [VISION_MODEL] }],
  ])('stays quiet when %s', async (_why, models) => {
    configureModels(models);
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.png'));

    expect(kit.visionToast).not.toHaveBeenCalled();
  });

  it('still warns when the vision fallback model does not see images either', async () => {
    configureModels({ visionFallback: VISION_MODEL });
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.png'));

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('image');
  });

  it('stays quiet for files that are not images, even when the models see nothing', async () => {
    configureModels({});
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.pdf'), makeFile('b.txt'), makeFile('c.mp3'));

    expect(kit.visionToast).not.toHaveBeenCalled();
  });

  it('stays quiet when no default model is configured', async () => {
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.png'), makeFile('b.mp4'));

    expect(kit.visionToast).not.toHaveBeenCalled();
  });

  it('stays quiet when the base model slot is empty', async () => {
    configureModels({ base: null });
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('a.png'));

    expect(kit.visionToast).not.toHaveBeenCalled();
  });
});

describe('AttachButton warning that the models cannot take video', () => {
  it('warns for a video, and still uploads it', async () => {
    configureModels({});
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('clip.MP4'));

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('video');
    expect(view.list.current.map((file) => file.fileName)).toEqual(['clip.MP4']);
  });

  it.each([
    ['the base model takes video', { video: [BASE_MODEL] }],
    ['a video fallback model takes video', { videoFallback: VIDEO_MODEL, video: [VIDEO_MODEL] }],
    ['a vision fallback model can read frames', { visionFallback: VISION_MODEL, vision: [VISION_MODEL] }],
  ])('stays quiet when %s', async (_why, models) => {
    configureModels(models);
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('clip.mp4'));

    expect(kit.visionToast).not.toHaveBeenCalled();
  });

  it('warns about the images first when a pick has both and the models take neither', async () => {
    configureModels({});
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('clip.mp4'), makeFile('a.png'));

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('image');
  });

  it('warns about the video when the models see images but cannot take video', async () => {
    configureModels({ vision: [BASE_MODEL] });
    const view = renderAttach();

    await pickFiles(view.input(), makeFile('clip.mp4'), makeFile('a.png'));

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('video');
  });
});
