demo/
├── pyproject.toml              # UV dependency management
├── uv.lock                     # Lock file
│
├── src/
│   ├── data_generation/
│   │   ├── __init__.py
│   │   ├── scraper.py          
│   │   ├── synthetic_generator.py  
│   │   ├── data_validator.py   
│   │   └── seeds/
│   │       └── real_hotels.json
│   │
│   ├── model/
│   │   ├── __init__.py
│   │   ├── embeddings.py       
│   │   ├── vector_store.py     
│   │   ├── search_engine.py    
│   │   └── llm_wrapper.py      
│   │
│   └── streamlit_app.py        
│
├── data/
│   ├── hotels.json             
│   └── chroma_db/              
│
├── .env.example
└── README.md

# Setup:
uv venv
uv pip install -e .
uv run python src/data_generation/synthetic_generator.py
uv run streamlit run src/streamlit_app.py