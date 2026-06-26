/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import {
  isImageFile,
  isVideoFile,
  isAudioFile,
  isPdfFile,
  isDocumentFile,
  isTextFile,
  getMimeType,
  getFileExtension,
  partitionFilesByType,
  fetchFileAsBase64DataURL,
  computeFileHash,
} from '../fileUtils';
import type { File } from '@/store/chat/types';

describe('fileUtils', () => {
  describe('isImageFile', () => {
    it('should return true for image extensions', () => {
      const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'];
      imageExtensions.forEach((ext) => {
        expect(isImageFile(ext)).toBe(true);
      });
    });

    it('should handle uppercase extensions', () => {
      expect(isImageFile('JPG')).toBe(true);
      expect(isImageFile('PNG')).toBe(true);
      expect(isImageFile('WEBP')).toBe(true);
    });

    it('should return false for non-image extensions', () => {
      expect(isImageFile('pdf')).toBe(false);
      expect(isImageFile('txt')).toBe(false);
      expect(isImageFile('doc')).toBe(false);
    });
  });

  describe('isVideoFile', () => {
    it('should return true for video extensions', () => {
      for (const ext of ['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v']) {
        expect(isVideoFile(ext)).toBe(true);
      }
    });

    it('should handle uppercase extensions', () => {
      expect(isVideoFile('MP4')).toBe(true);
      expect(isVideoFile('MOV')).toBe(true);
    });

    it('should return false for non-video extensions', () => {
      expect(isVideoFile('mp3')).toBe(false);
      expect(isVideoFile('jpg')).toBe(false);
      expect(isVideoFile('pdf')).toBe(false);
    });
  });

  describe('isAudioFile', () => {
    it('should return true for all supported audio extensions', () => {
      for (const ext of ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma', 'opus']) {
        expect(isAudioFile(ext)).toBe(true);
      }
    });

    it('should handle uppercase extensions', () => {
      expect(isAudioFile('MP3')).toBe(true);
      expect(isAudioFile('WAV')).toBe(true);
      expect(isAudioFile('OPUS')).toBe(true);
    });

    it('should return false for non-audio extensions', () => {
      expect(isAudioFile('mp4')).toBe(false);
      expect(isAudioFile('jpg')).toBe(false);
      expect(isAudioFile('pdf')).toBe(false);
      expect(isAudioFile('webm')).toBe(false);
    });
  });

  describe('isPdfFile', () => {
    it('should return true for pdf extension', () => {
      expect(isPdfFile('pdf')).toBe(true);
    });

    it('should handle uppercase pdf extension', () => {
      expect(isPdfFile('PDF')).toBe(true);
    });

    it('should return false for non-pdf extensions', () => {
      expect(isPdfFile('jpg')).toBe(false);
      expect(isPdfFile('txt')).toBe(false);
    });
  });

  describe('isDocumentFile', () => {
    it('should return true for document extensions', () => {
      expect(isDocumentFile('docx')).toBe(true);
      expect(isDocumentFile('xlsx')).toBe(true);
      expect(isDocumentFile('xls')).toBe(true);
    });

    it('should handle uppercase', () => {
      expect(isDocumentFile('DOCX')).toBe(true);
      expect(isDocumentFile('XLSX')).toBe(true);
    });

    it('should return false for non-document extensions', () => {
      expect(isDocumentFile('pdf')).toBe(false);
      expect(isDocumentFile('txt')).toBe(false);
      expect(isDocumentFile('jpg')).toBe(false);
    });
  });

  describe('isTextFile', () => {
    it('should return true for text extensions', () => {
      expect(isTextFile('csv')).toBe(true);
      expect(isTextFile('txt')).toBe(true);
      expect(isTextFile('md')).toBe(true);
      expect(isTextFile('json')).toBe(true);
    });

    it('should handle uppercase', () => {
      expect(isTextFile('CSV')).toBe(true);
      expect(isTextFile('JSON')).toBe(true);
    });

    it('should return false for non-text extensions', () => {
      expect(isTextFile('pdf')).toBe(false);
      expect(isTextFile('docx')).toBe(false);
      expect(isTextFile('jpg')).toBe(false);
    });
  });

  describe('getMimeType', () => {
    it('should return correct MIME types for image formats', () => {
      expect(getMimeType('jpg')).toBe('image/jpeg');
      expect(getMimeType('jpeg')).toBe('image/jpeg');
      expect(getMimeType('png')).toBe('image/png');
      expect(getMimeType('gif')).toBe('image/gif');
      expect(getMimeType('webp')).toBe('image/webp');
      expect(getMimeType('bmp')).toBe('image/bmp');
    });

    it('should return correct MIME type for pdf', () => {
      expect(getMimeType('pdf')).toBe('application/pdf');
    });

    it('should return correct MIME types for document formats', () => {
      expect(getMimeType('docx')).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');
      expect(getMimeType('xlsx')).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      expect(getMimeType('xls')).toBe('application/vnd.ms-excel');
      expect(getMimeType('csv')).toBe('text/csv');
      expect(getMimeType('txt')).toBe('text/plain');
      expect(getMimeType('md')).toBe('text/markdown');
      expect(getMimeType('json')).toBe('application/json');
    });

    it('should return correct MIME types for audio formats', () => {
      expect(getMimeType('mp3')).toBe('audio/mpeg');
      expect(getMimeType('wav')).toBe('audio/wav');
      expect(getMimeType('ogg')).toBe('audio/ogg');
      expect(getMimeType('flac')).toBe('audio/flac');
      expect(getMimeType('m4a')).toBe('audio/mp4');
      expect(getMimeType('aac')).toBe('audio/aac');
      expect(getMimeType('wma')).toBe('audio/x-ms-wma');
      expect(getMimeType('opus')).toBe('audio/opus');
    });

    it('should return correct MIME types for video formats', () => {
      expect(getMimeType('mp4')).toBe('video/mp4');
      expect(getMimeType('mov')).toBe('video/quicktime');
      expect(getMimeType('webm')).toBe('video/webm');
      expect(getMimeType('avi')).toBe('video/x-msvideo');
      expect(getMimeType('mkv')).toBe('video/x-matroska');
      expect(getMimeType('wmv')).toBe('video/x-ms-wmv');
      expect(getMimeType('m4v')).toBe('video/x-m4v');
    });

    it('should return octet-stream for unknown extensions', () => {
      expect(getMimeType('unknown')).toBe('application/octet-stream');
      expect(getMimeType('')).toBe('application/octet-stream');
    });

    it('should handle uppercase extensions', () => {
      expect(getMimeType('PNG')).toBe('image/png');
      expect(getMimeType('PDF')).toBe('application/pdf');
    });
  });

  describe('getFileExtension', () => {
    it('should extract extension from filename', () => {
      expect(getFileExtension('document.pdf')).toBe('pdf');
      expect(getFileExtension('image.jpg')).toBe('jpg');
      expect(getFileExtension('archive.tar.gz')).toBe('gz');
    });

    it('should handle filenames without extension', () => {
      expect(getFileExtension('README')).toBe('readme');
    });

    it('should handle empty filename', () => {
      expect(getFileExtension('')).toBe('');
    });

    it('should return lowercase extension', () => {
      expect(getFileExtension('IMAGE.PNG')).toBe('png');
    });
  });

  describe('partitionFilesByType', () => {
    const createMockFile = (fileName: string, ext: string): File => ({
      id: `id-${fileName}`,
      fileName,
      fileExtension: ext,
      fileUrl: `http://example.com/${fileName}`,
      fileType: 'uploaded',
    });

    it('should partition files into all categories', () => {
      const files: File[] = [
        createMockFile('photo.jpg', 'jpg'),
        createMockFile('document.pdf', 'pdf'),
        createMockFile('report.docx', 'docx'),
        createMockFile('data.csv', 'csv'),
        createMockFile('unknown.xyz', 'xyz'),
      ];

      const result = partitionFilesByType(files);

      expect(result.imageFiles).toHaveLength(1);
      expect(result.pdfFiles).toHaveLength(1);
      expect(result.documentFiles).toHaveLength(1);
      expect(result.textFiles).toHaveLength(1);
      expect(result.otherFiles).toHaveLength(1);
      expect(result.imageFiles[0].fileName).toBe('photo.jpg');
      expect(result.pdfFiles[0].fileName).toBe('document.pdf');
      expect(result.documentFiles[0].fileName).toBe('report.docx');
      expect(result.textFiles[0].fileName).toBe('data.csv');
      expect(result.otherFiles[0].fileName).toBe('unknown.xyz');
    });

    it('should handle empty file list', () => {
      const result = partitionFilesByType([]);

      expect(result.imageFiles).toHaveLength(0);
      expect(result.pdfFiles).toHaveLength(0);
      expect(result.documentFiles).toHaveLength(0);
      expect(result.textFiles).toHaveLength(0);
      expect(result.otherFiles).toHaveLength(0);
    });

    it('should categorize all image types correctly', () => {
      const imageFiles: File[] = [
        createMockFile('1.jpg', 'jpg'),
        createMockFile('2.jpeg', 'jpeg'),
        createMockFile('3.png', 'png'),
        createMockFile('4.gif', 'gif'),
        createMockFile('5.webp', 'webp'),
        createMockFile('6.bmp', 'bmp'),
      ];

      const result = partitionFilesByType(imageFiles);

      expect(result.imageFiles).toHaveLength(6);
      expect(result.pdfFiles).toHaveLength(0);
      expect(result.documentFiles).toHaveLength(0);
      expect(result.textFiles).toHaveLength(0);
      expect(result.otherFiles).toHaveLength(0);
    });

    it('should categorize all document types correctly', () => {
      const docFiles: File[] = [
        createMockFile('report.docx', 'docx'),
        createMockFile('data.xlsx', 'xlsx'),
        createMockFile('legacy.xls', 'xls'),
      ];

      const result = partitionFilesByType(docFiles);

      expect(result.documentFiles).toHaveLength(3);
      expect(result.imageFiles).toHaveLength(0);
      expect(result.pdfFiles).toHaveLength(0);
      expect(result.textFiles).toHaveLength(0);
      expect(result.otherFiles).toHaveLength(0);
    });

    it('should categorize audio files into otherFiles bucket', () => {
      const audioFiles: File[] = [
        createMockFile('song.mp3', 'mp3'),
        createMockFile('recording.wav', 'wav'),
        createMockFile('voice.opus', 'opus'),
      ];

      const result = partitionFilesByType(audioFiles);

      expect(result.otherFiles).toHaveLength(3);
      expect(result.imageFiles).toHaveLength(0);
      expect(result.videoFiles).toHaveLength(0);
    });

    it('should handle mixed file types including audio', () => {
      const mixedFiles: File[] = [
        createMockFile('photo.jpg', 'jpg'),
        createMockFile('video.mp4', 'mp4'),
        createMockFile('song.mp3', 'mp3'),
        createMockFile('doc.pdf', 'pdf'),
      ];

      const result = partitionFilesByType(mixedFiles);

      expect(result.imageFiles).toHaveLength(1);
      expect(result.videoFiles).toHaveLength(1);
      expect(result.pdfFiles).toHaveLength(1);
      expect(result.otherFiles).toHaveLength(1);
      expect(result.otherFiles[0].fileName).toBe('song.mp3');
    });

    it('should categorize all text types correctly', () => {
      const textFiles: File[] = [
        createMockFile('data.csv', 'csv'),
        createMockFile('notes.txt', 'txt'),
        createMockFile('readme.md', 'md'),
        createMockFile('config.json', 'json'),
      ];

      const result = partitionFilesByType(textFiles);

      expect(result.textFiles).toHaveLength(4);
      expect(result.imageFiles).toHaveLength(0);
      expect(result.pdfFiles).toHaveLength(0);
      expect(result.documentFiles).toHaveLength(0);
      expect(result.otherFiles).toHaveLength(0);
    });
  });

  describe('fetchFileAsBase64DataURL', () => {
    it('should convert file to base64 data URL', async () => {
      const mockBlob = new Blob(['test content'], { type: 'text/plain' });
      const mockResponse = {
        ok: true,
        blob: () => Promise.resolve(mockBlob),
      };

      vi.spyOn(global, 'fetch').mockResolvedValueOnce(mockResponse as Response);

      const result = await fetchFileAsBase64DataURL('http://example.com/file.txt', 'text/plain');

      expect(result).toMatch(/^data:text\/plain;base64,/);
      expect(fetch).toHaveBeenCalledWith('http://example.com/file.txt');
    });
  });

  describe('computeFileHash', () => {
    const createMockFileWithArrayBuffer = (content: string): Blob => {
      const encoder = new TextEncoder();
      const data = encoder.encode(content);
      const blob = new Blob([data]);
      if (typeof blob.arrayBuffer !== 'function') {
        blob.arrayBuffer = () => Promise.resolve(data.buffer as ArrayBuffer);
      }
      return blob;
    };

    it('should compute SHA-256 hash of a file', async () => {
      const mockFile = createMockFileWithArrayBuffer('test content');

      const hash = await computeFileHash(mockFile);

      expect(hash).toMatch(/^[a-f0-9]{64}$/);
    });

    it('should return consistent hash for same content', async () => {
      const file1 = createMockFileWithArrayBuffer('hello world');
      const file2 = createMockFileWithArrayBuffer('hello world');

      const hash1 = await computeFileHash(file1);
      const hash2 = await computeFileHash(file2);

      expect(hash1).toBe(hash2);
    });

    it('should return different hashes for different content', async () => {
      const file1 = createMockFileWithArrayBuffer('content 1');
      const file2 = createMockFileWithArrayBuffer('content 2');

      const hash1 = await computeFileHash(file1);
      const hash2 = await computeFileHash(file2);

      expect(hash1).not.toBe(hash2);
    });
  });
});
