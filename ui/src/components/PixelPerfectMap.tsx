import React, { useRef, useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

interface Territory {
  name: string;
  owner: string;
  owner_color: string;
  units: number;
  type: string;
  image_id: string;
  adjacent: string[];
}

interface PixelPerfectMapProps {
  territories: Record<string, Territory>;
  onTerritoryClick: (territory: Territory) => void;
  selectedTerritory: Territory | null;
  targetTerritory: Territory | null;
  hoveredPlayer: string | null;
  highlightedTerritory: string | null;
  lastActedTerritory: string | null;
  isJollyHovered: boolean;
}

const MAP_WIDTH = 1227;
const MAP_HEIGHT = 628;

export const PixelPerfectMap: React.FC<PixelPerfectMapProps> = ({ 
  territories, 
  onTerritoryClick,
  selectedTerritory,
  targetTerritory,
  hoveredPlayer,
  highlightedTerritory,
  lastActedTerritory,
  isJollyHovered
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasesRef = useRef<Record<string, HTMLCanvasElement>>({});
  const [centroids, setCentroids] = useState<Record<string, { x: number, y: number }>>({});
  const [hoveredTerritory, setHoveredTerritory] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  // Initialize canvases for hit testing and calculate centroids
  useEffect(() => {
    const territoryList = Object.values(territories);
    let loadedCount = 0;
    const newCentroids: Record<string, { x: number, y: number }> = {};

    territoryList.forEach((t) => {
      const img = new Image();
      img.src = `/assets/states/${t.image_id}.png`;
      img.crossOrigin = "anonymous";
      
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = MAP_WIDTH;
        canvas.height = MAP_HEIGHT;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          canvasesRef.current[t.name] = canvas;
          
          // Calculate centroid
          const imageData = ctx.getImageData(0, 0, MAP_WIDTH, MAP_HEIGHT).data;
          let sumX = 0, sumY = 0, count = 0;
          for (let y = 0; y < MAP_HEIGHT; y++) {
            for (let x = 0; x < MAP_WIDTH; x++) {
              const alpha = imageData[(y * MAP_WIDTH + x) * 4 + 3];
              if (alpha > 10) {
                sumX += x;
                sumY += y;
                count++;
              }
            }
          }
          if (count > 0) {
            newCentroids[t.name] = { x: sumX / count, y: sumY / count };
          }
        }
        loadedCount++;
        if (loadedCount === territoryList.length) {
          setCentroids(newCentroids);
          setIsLoaded(true);
        }
      };
    });
  }, [territories]);

  const findTerritoryAt = useCallback((x: number, y: number) => {
    const territoryNames = Object.keys(territories).reverse();
    for (const name of territoryNames) {
      const canvas = canvasesRef.current[name];
      if (!canvas) continue;
      const ctx = canvas.getContext('2d');
      if (!ctx) continue;
      const pixel = ctx.getImageData(x, y, 1, 1).data;
      if (pixel[3] > 10) return name;
    }
    return null;
  }, [territories]);

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * MAP_WIDTH);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * MAP_HEIGHT);
    if (x >= 0 && x < MAP_WIDTH && y >= 0 && y < MAP_HEIGHT) {
      setHoveredTerritory(findTerritoryAt(x, y));
    } else {
      setHoveredTerritory(null);
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * MAP_WIDTH);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * MAP_HEIGHT);
    const hit = findTerritoryAt(x, y);
    if (hit) onTerritoryClick(territories[hit]);
  };

  return (
    <div 
      ref={containerRef}
      className="map-container"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoveredTerritory(null)}
      onClick={handleClick}
      style={{ cursor: hoveredTerritory ? 'pointer' : 'default' }}
    >
      {Object.values(territories).map((t) => {
        const isDimmed = (hoveredPlayer && t.owner !== hoveredPlayer) || (isJollyHovered && t.owner !== territories[Object.keys(territories)[0]].owner); 
        // Note: For Jolly, the user said "grayed out", I'll interpret as dimming everything except current player's
        // Actually, if it's Jolly, let's dim EVERYTHING except the player's own territories.
        
        const isActed = lastActedTerritory === t.name;
        const isFocused = hoveredTerritory === t.name || 
                          selectedTerritory?.name === t.name || 
                          targetTerritory?.name === t.name ||
                          highlightedTerritory === t.name;

        return (
          <React.Fragment key={t.name}>
            <motion.img
              src={`/assets/states/${t.image_id}.png`}
              className={`territory-layer ${isActed ? 'acted-glow' : ''}`}
              animate={{ 
                opacity: isDimmed ? 0.2 : 1,
                filter: isFocused
                  ? `brightness(1.5) drop-shadow(0 0 20px ${t.owner_color})` 
                  : (isActed ? `brightness(1.2) drop-shadow(0 0 15px #fff)` : `brightness(1) drop-shadow(0 0 4px ${t.owner_color})`),
                scale: isFocused ? 1.01 : 1,
                saturate: isDimmed || isJollyHovered ? 0 : 1,
              }}
              transition={{ duration: 0.2 }}
              style={{ 
                pointerEvents: 'none',
                zIndex: isFocused ? 5 : 1
              }}
            />
            {/* Troop Badge at Centroid */}
            {isLoaded && centroids[t.name] && (
              <motion.div
                className="troop-badge"
                animate={{ 
                  scale: isFocused ? 1.2 : 1,
                  opacity: isDimmed ? 0.2 : 1 
                }}
                style={{
                  position: 'absolute',
                  left: `${(centroids[t.name].x / MAP_WIDTH) * 100}%`,
                  top: `${(centroids[t.name].y / MAP_HEIGHT) * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  zIndex: 10,
                  backgroundColor: t.owner_color,
                  pointerEvents: 'none'
                }}
              >
                {t.units}
              </motion.div>
            )}
          </React.Fragment>
        );
      })}

      {/* Adjacency Graph Layer */}
      {isLoaded && (
        <svg 
          style={{ 
            position: 'absolute', 
            top: 0, 
            left: 0, 
            width: '100%', 
            height: '100%', 
            pointerEvents: 'none',
            zIndex: 2,
            opacity: 0.4
          }}
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>
          {Object.entries(territories).map(([name, t]) => {
            const start = centroids[name];
            if (!start) return null;

            return t.adjacent.map(adjName => {
              const end = centroids[adjName];
              if (!end || name > adjName) return null; // Draw each edge only once

              return (
                <line
                  key={`${name}-${adjName}`}
                  x1={`${(start.x / MAP_WIDTH) * 100}%`}
                  y1={`${(start.y / MAP_HEIGHT) * 100}%`}
                  x2={`${(end.x / MAP_WIDTH) * 100}%`}
                  y2={`${(end.y / MAP_HEIGHT) * 100}%`}
                  stroke="rgba(99, 102, 241, 0.5)"
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                  filter="url(#glow)"
                />
              );
            });
          })}
        </svg>
      )}

      {!isLoaded && (
        <div className="map-loading-overlay">
          Scanning Battlefield...
        </div>
      )}
    </div>
  );
};
