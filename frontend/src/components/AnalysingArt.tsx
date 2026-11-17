/**
 * The analysis screen's picture: a girl in cat-ear headphones sipping tea while hit circles come and go. Drawn for
 * osu! coach (not osu!'s own mascot); the motion stops with "reduce motion" (see .analysing-art in components.css).
 */
export function AnalysingArt() {
  return (
    <svg className="analysing-art" viewBox="0 0 320 240" role="img" aria-label="A girl in headphones relaxing with a cup of tea next to three hit circles">
      <defs>
        <radialGradient id="aa-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#ff70b8" stopOpacity=".32" />
          <stop offset=".6" stopColor="#b8a3ff" stopOpacity=".16" />
          <stop offset="1" stopColor="#b8a3ff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="aa-pink" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#ff8cc6" /><stop offset="1" stopColor="#ff5aa5" /></linearGradient>
        <linearGradient id="aa-violet" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#c7b6ff" /><stop offset="1" stopColor="#9a80ff" /></linearGradient>
        <linearGradient id="aa-blue" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#8fdcff" /><stop offset="1" stopColor="#4fb8f0" /></linearGradient>
        <linearGradient id="aa-hair" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#7a58bd" /><stop offset="1" stopColor="#553a8c" /></linearGradient>
        <linearGradient id="aa-hoodie" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#ffa3d2" /><stop offset="1" stopColor="#ff79b9" /></linearGradient>
      </defs>
      <circle cx="160" cy="128" r="112" fill="url(#aa-glow)" />

      <g className="analysing-art__sparkles">
        <path d="M52 64 l3 9 9 3 -9 3 -3 9 -3 -9 -9 -3 9 -3z" fill="#ffd1e8" />
        <path d="M38 142 l2 6 6 2 -6 2 -2 6 -2 -6 -6 -2 6 -2z" fill="#c7b6ff" />
        <path d="M74 196 l2.5 7 7 2.5 -7 2.5 -2.5 7 -2.5 -7 -7 -2.5 7 -2.5z" fill="#8fdcff" />
      </g>
      <g className="analysing-art__note">
        <path d="M70 92 v-22 l16 -5 v20" fill="none" stroke="#ff8cc6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <ellipse cx="66" cy="93" rx="5.5" ry="4.2" fill="#ff8cc6" />
        <ellipse cx="82" cy="86" rx="5.5" ry="4.2" fill="#ff8cc6" />
      </g>

      <g className="analysing-art__circles" fontFamily="Inter, system-ui, sans-serif" fontWeight="800" fontSize="17" textAnchor="middle" fill="#fff">
        <circle className="analysing-art__approach" cx="262" cy="80" r="31" fill="none" stroke="#ff8cc6" strokeWidth="2.5" />
        <g className="analysing-art__circle"><circle cx="262" cy="80" r="18" fill="url(#aa-pink)" stroke="#fff" strokeWidth="3" /><text x="262" y="86">1</text></g>
        <g className="analysing-art__circle"><circle cx="288" cy="136" r="18" fill="url(#aa-violet)" stroke="#fff" strokeWidth="3" /><text x="288" y="142">2</text></g>
        <g className="analysing-art__circle"><circle cx="254" cy="190" r="18" fill="url(#aa-blue)" stroke="#fff" strokeWidth="3" /><text x="254" y="196">3</text></g>
      </g>

      <path d="M98 128 C92 78 122 54 150 54 C178 54 208 78 202 128 C206 156 201 182 193 198 L107 198 C99 182 94 156 98 128 Z" fill="url(#aa-hair)" />
      <path d="M110 172 C110 160 124 154 150 154 C176 154 190 160 190 172 L197 216 C198 224 192 230 183 230 L117 230 C108 230 102 224 103 216 Z" fill="url(#aa-hoodie)" />
      <path d="M132 156 L150 172 L168 156" fill="none" stroke="#ffd1e8" strokeWidth="3" strokeLinejoin="round" />

      <g className="analysing-art__head">
        <ellipse cx="150" cy="116" rx="44" ry="40" fill="#ffe8de" />
        <path d="M106 114 C102 84 122 64 150 64 C178 64 198 84 194 114 C188 102 181 94 172 91 L169 106 L159 88 L150 104 L141 88 L131 106 L128 91 C119 94 112 102 106 114 Z" fill="url(#aa-hair)" />
        <path d="M106 108 C99 132 103 152 113 164 C110 142 112 124 115 110 Z" fill="#6a49a6" />
        <path d="M194 108 C201 132 197 152 187 164 C190 142 188 124 185 110 Z" fill="#6a49a6" />
        <path d="M128 76 C136 70 146 68 154 69" fill="none" stroke="#9c7ee0" strokeWidth="3" strokeLinecap="round" opacity=".8" />
        <g fill="none" stroke="#3b2457" strokeWidth="3.2" strokeLinecap="round">
          <path d="M124 121 Q133 129 142 121" />
          <path d="M158 121 Q167 129 176 121" />
          <path d="M124 121 l-4 -3 M176 121 l4 -3" />
        </g>
        <ellipse cx="126" cy="134" rx="8.5" ry="4.5" fill="#ff8cc6" opacity=".55" />
        <ellipse cx="174" cy="134" rx="8.5" ry="4.5" fill="#ff8cc6" opacity=".55" />
        <path d="M143 137 Q146.5 141.5 150 138 Q153.5 141.5 157 137" fill="none" stroke="#c4527f" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M112 66 L104 36 L134 56 Z" fill="#ff70b8" />
        <path d="M114 60 L110 45 L125 56 Z" fill="#ffd1e8" />
        <path d="M188 66 L196 36 L166 56 Z" fill="#ff70b8" />
        <path d="M186 60 L190 45 L175 56 Z" fill="#ffd1e8" />
        <path d="M97 114 C93 46 207 46 203 114" fill="none" stroke="#ff70b8" strokeWidth="9" strokeLinecap="round" />
        <rect x="86" y="98" width="22" height="36" rx="10" fill="#ff70b8" />
        <rect x="91" y="104" width="12" height="24" rx="6" fill="#ffd1e8" />
        <rect x="192" y="98" width="22" height="36" rx="10" fill="#ff70b8" />
        <rect x="197" y="104" width="12" height="24" rx="6" fill="#ffd1e8" />
      </g>

      <g className="analysing-art__steam" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" fill="none">
        <path d="M143 178 C139 172 147 168 143 162" />
        <path d="M151 176 C147 170 155 166 151 158" />
        <path d="M159 178 C155 172 163 168 159 162" />
      </g>
      <path d="M164 190 C176 190 176 206 164 206" fill="none" stroke="#f3cfe1" strokeWidth="4.5" />
      <rect x="134" y="182" width="32" height="30" rx="7" fill="#fff7fb" />
      <circle cx="150" cy="197" r="7" fill="none" stroke="#ff70b8" strokeWidth="3" />
      <ellipse cx="133" cy="203" rx="7.5" ry="6.5" fill="#ffe8de" />
      <ellipse cx="166" cy="208" rx="7" ry="6" fill="#ffe8de" />
    </svg>
  );
}
