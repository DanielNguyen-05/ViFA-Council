import ReactMarkdown from 'react-markdown';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  const selectedModel = finalResponse.model || finalResponse.selected_model;
  const chairmanModel = finalResponse.chairman_model;
  const responseText = finalResponse.response || finalResponse.selected_response || '';

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Chairman Selection</h3>
      <div className="final-response">
        <div className="chairman-label">
          Selected candidate: {finalResponse.selected_label || 'Unknown'}
          {' · '}
          Model: {selectedModel || 'Unknown'}
          {chairmanModel ? ` · Chairman: ${chairmanModel}` : ''}
        </div>
        {finalResponse.selected_stage && (
          <div className="selection-meta">
            {finalResponse.selected_stage}
            {' · '}
            {finalResponse.schema_valid ? 'Schema validated' : 'Schema validation failed'}
          </div>
        )}
        <div className="final-text markdown-content">
          <ReactMarkdown>{responseText}</ReactMarkdown>
        </div>
        {finalResponse.generated_images?.length > 0 && (
          <div className="generated-images">
            {finalResponse.generated_images.map((image) => (
              <figure className="generated-image" key={`${image.step}-${image.url}`}>
                <img src={image.url} alt={`Generated result ${image.step}`} />
                <figcaption>
                  {finalResponse.task_type === 'story_generation'
                    ? `Panel ${image.step}`
                    : 'Generated outpainting'}
                  {image.model ? ` · ${image.model}` : ''}
                </figcaption>
              </figure>
            ))}
          </div>
        )}
        {finalResponse.synthesis_error && (
          <div className="synthesis-error">{finalResponse.synthesis_error}</div>
        )}
        {finalResponse.evaluation && (
          <details className="chairman-evaluation">
            <summary>Chairman evaluation</summary>
            <div className="markdown-content">
              <ReactMarkdown>{finalResponse.evaluation}</ReactMarkdown>
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
