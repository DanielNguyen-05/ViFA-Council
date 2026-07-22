import { useState } from "react";
import ReactMarkdown from "react-markdown";
import "./Stage2.css";

export default function Stage2({ results }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!results || results.length === 0) return null;
  console.log(results);

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Cross Refinement</h3>

      <div className="tabs">
        {results.map((item, index) => {
          const refiner =
            item.stage2_model?.split("/")[1] || item.stage2_model;

          return (
            <button
              key={index}
              className={`tab ${activeTab === index ? "active" : ""}`}
              onClick={() => setActiveTab(index)}
            >
              {refiner}
            </button>
          );
        })}
      </div>

      {results[activeTab] && (
        <div className="tab-content">
          <div className="refinement-meta">
            <div>
              <strong>Original model:</strong>{" "}
              {results[activeTab].original_model}
            </div>
            <div>
              <strong>Refined by:</strong>{" "}
              {results[activeTab].stage2_model}
            </div>
          </div>

          <div className="refinement-block perfected">
            <h4>Refined Response</h4>
            <div className="markdown-content">
              <ReactMarkdown>
                {results[activeTab].perfected_response}
              </ReactMarkdown>
              
            </div>
          </div>
        </div>
      )}
    </div>
  );
}