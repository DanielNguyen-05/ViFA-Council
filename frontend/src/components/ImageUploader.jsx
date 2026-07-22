"use client";

import { AlertCircleIcon, Plus, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useFileUpload } from "@/hooks/use-file-upload";
import { useEffect } from "react";

export default function ImageUploader({ onChangeImage }) {
  const maxSizeMB = 5;
  const maxSize = maxSizeMB * 1024 * 1024;
  const maxFiles = 1;

  const [
    { files, errors },
    {
      openFileDialog,
      removeFile,
      getInputProps,
    },
  ] = useFileUpload({
    accept: "image/png,image/jpeg,image/webp",
    maxFiles,
    maxSize,
    multiple: false,
  });

  useEffect(() => {
    onChangeImage(files);
  }, [files, onChangeImage]);

  return (
    <div className="w-full">
      {files.length > 0 && (
        <div className="flex gap-2 overflow-x-auto rounded-md bg-muted/30 p-1">
          {files.map((file) => (
            <div
              key={file.id}
              className="relative h-16 w-16 shrink-0 rounded-md border bg-muted"
            >
              <img
                src={file.preview}
                alt={file.file.name}
                className="h-full w-full rounded-md object-cover"
              />
              <Button
                type="button"
                size="icon"
                variant="secondary"
                className="absolute -top-1 -right-1 h-5 w-5 rounded-full"
                onClick={() => removeFile(file.id)}
              >
                <XIcon className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="absolute bottom-2 right-2">
        <input {...getInputProps()} className="sr-only" />

        <button
          type="button"
          onClick={openFileDialog}
          className="bg-[#357abd] hover:bg-[#2a5d91] text-white rounded-full size-8 flex items-center justify-center"
        >
          <Plus className="size-4" />
        </button>
      </div>

      {errors.length > 0 && (
        <div className="mt-1 flex items-center gap-1 text-destructive text-xs">
          <AlertCircleIcon className="size-3 shrink-0" />
          <span>{errors[0]}</span>
        </div>
      )}
    </div>
  );
}
