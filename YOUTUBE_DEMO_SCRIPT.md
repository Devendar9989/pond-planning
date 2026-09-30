# 5-Minute Public YouTube Demo & Presentation Script
## Project: Autonomous Contour-Based Farm Pond Siting & Catchment Delineation (PondPlan AI)

---

### Overview & Video Objectives
* **Target Video Length:** ~4 to 5 minutes (Maximum allowed: 5:00)
* **YouTube Video Demo Link:** `https://www.youtube.com/playlist?list=PLMFQLz-BMw9M`
* **Working Front-End URL to Showcase (Primary):** `http://10.1.75.51:6241/`
* **Alternative Front-End URLs:** `http://10.1.75.51:5241/` and `http://10.1.75.51:3241/`
* **API Documentation to Showcase:** `http://10.1.75.51:6241/docs`
* **GitHub Repository:** `https://github.com/Devendar9989/pond-planning`

---

### Segment-by-Segment Video Script & Walkthrough

```
+-----------------------------------------------------------------------------------------------+
| Timeline | Section                | Visual on Screen                   | Spoken Narration     |
+-----------------------------------------------------------------------------------------------+
| 0:00-0:45| 1. Introduction & Goal | Front-End Landing Page at          | Problem & Project    |
|          |                        | http://10.1.75.51:6241/            | Objectives           |
| 0:45-1:45| 2. Core Hydrological   | Architecture diagram & code view   | Pure-NumPy Algorithm |
|          |    Algorithms          | (Priority-Flood, D8, O(N) DAG)     | Flow & Formulation   |
| 1:45-3:15| 3. Live Demo (Map,     | Browser interacting with map,      | Live Land Selection, |
|          |    Land AOI & Siting)  | drawing land parcel, clicking Run  | Overlay & Results    |
| 3:15-4:15| 4. Water Harvesting    | Adjusting Rainfall & Soil sliders, | Rational Runoff &    |
|          |    Volume Calculator   | viewing Olympic pool metrics       | Agricultural Impact  |
| 4:15-5:00| 5. Multi-System Scaling| Swagger API, Pytest suite (25/25), | Scaling Architecture |
|          |    & Conclusion        | GitHub repo & Overleaf report      | & Closing Remarks    |
+-----------------------------------------------------------------------------------------------+
```

---

### Detailed Script & Narration

#### 🕒 [0:00 – 0:45] Section 1: Introduction & Problem Statement
* **Visual:** Open browser at `http://10.1.75.51:6241/`. Show the clean Leaflet map with satellite imagery and the control sidebar.
* **Speaker Script:**
> *"Hello everyone. Today I am demonstrating **PondPlan AI**, an autonomous geospatial system for contour-based farm pond siting, catchment boundary delineation, and water harvest volume estimation.*
> *In dryland agriculture, strategically placing farm ponds is crucial for drought resilience. However, manual topographical surveying across hectares of land is expensive and time-consuming. Our platform takes raw contour survey files in KML or KMZ formats, performs automated hydrological modeling, and identifies the optimal pond outlet site and harvestable water volume within seconds—all running on a lightweight, resource-constrained server."*

---

#### 🕒 [0:45 – 1:45] Section 2: Core Hydrological Algorithms & Pure-NumPy Engine
* **Visual:** Briefly show the architecture diagram or the code in `app/terrain/hydrology.py` and `app/dem/dem_builder.py`.
* **Speaker Script:**
> *"To ensure high speed and run within strict 512MB RAM constraints, we eliminated heavy GIS libraries like GDAL and built a pure-NumPy hydrology pipeline:*
> *1. **Dynamic UTM Reprojection:** We auto-detect the local UTM EPSG zone from the survey centroid to convert geographic degrees into exact metric meters.*
> *2. **Priority-Flood Depression Filling:** We implement Barnes et al.'s O(N log N) priority queue algorithm using Python's heapq to eliminate artificial digital sinks.*
> *3. **2nd-Order Slope & D8 Steepest Descent Routing:** We compute central difference gradient slopes and assign D8 flow directions.*
> *4. **O(N) In-Degree Topological Accumulation:** Flow accumulation is computed in linear O(N) time from ridge lines downward without recursive call-stack overhead.*
> *5. **Multi-Criteria Siting Heuristic:** We evaluate flow accumulation (70%), optimal slope below 8% (30%), and natural concave storage depression depth to pinpoint the optimal pond outlet."*

---

#### 🕒 [1:45 – 3:15] Section 3: Live System Demonstration & Map Interaction
* **Visual:** Return to `http://10.1.75.51:6241/`.
  1. Click **"Load Survey Map"** (or select `contours_1m.kml`).
  2. Click **"Draw Rectangle"** or **"Draw Polygon"** on the map to highlight a specific land parcel / farm area.
  3. Click **"Run Catchment Analysis"**.
  4. Watch the loading spinner and observe the map zoom directly into the delineated catchment boundary overlay and the animated water drop pond icon.
* **Speaker Script:**
> *"Now, let's see the live system in action.*
> *Here on the map, we have preloaded our 3.2km survey map `contours_1m.kml`. As a farmer or planner, you can use our built-in drawing tool to select a specific agricultural parcel on the map. Notice how the coordinates and boundaries update dynamically.*
> *When we click 'Run Catchment Analysis', the backend streams the file, reconstructs the DEM, models the drainage basin, and overlays the results:*
> *- The **cyan shaded polygon** represents the exact 44,300 square meter (4.43 hectare) upstream catchment area.*
> *- The **animated blue marker** indicates our suggested farm pond location at 270.0 meters elevation, perfectly positioned in the natural drainage channel with 310 upstream contributing cells.*
> *- We also see a vertical basin relief of 23.0 meters and an average terrain slope of 4.8%, which is ideal for runoff stability."*

---

#### 🕒 [3:15 – 4:15] Section 4: Expected Harvestable Water Volume Estimation
* **Visual:** Move to the **Catchment Analytics** tab. Interact with the **Annual Rainfall** slider (e.g. adjust from 1000mm to 1200mm) and change the **Soil Runoff Coefficient** (e.g. Agricultural Loam $C=0.35$ vs Clay $C=0.50$). Point to the live updated volume card, Olympic pool equivalents, and irrigation days.
* **Speaker Script:**
> *"Next is the **Expected Water Volume** estimation.*
> *Using the standard hydrological Rational Runoff equation—Volume equals Catchment Area times Rainfall times Runoff Coefficient C—our system calculates harvestable runoff volume in real time.*
> *For our 4.43-hectare catchment with 1000mm annual monsoon precipitation and a loam soil coefficient of 0.35, the expected annual harvestable water volume is **15,505 cubic meters**, or **15.51 Million Liters**.*
> *To make this intuitive for farmers, our dashboard translates this into real-world metrics: approximately **6.2 Olympic swimming pools**, providing over **31 days of full irrigation** for a 5-acre farm. Users can adjust rainfall and soil presets on the fly to test drought or high-monsoon scenarios."*

---

#### 🕒 [4:15 – 5:00] Section 5: Scaling, Multi-System Architecture & Conclusion
* **Visual:** Briefly show `/docs` (FastAPI Swagger UI), the terminal running `pytest` (25 passed), and the GitHub repository.
* **Speaker Script:**
> *"For multi-system scalability, our backend API is completely stateless, accepts standard multipart form data under `contour_map`, and is deployed with an auto-restarting watchdog daemon across our remote servers on ports 6000 (6241), 5000 (5241), and 3000 (3241).*
> *Our automated test suite covers 25 unit, integration, and synthetic topographic scenarios.*
> *Users can download the full GeoJSON boundary polygon or export the structured JSON report with a single click.*
> *Thank you for watching our demo of PondPlan AI. All links, including the live working front-end, GitHub repository, and technical report, are provided in the description below."*

---

### Tips for Recording
1. **Screen Recording:** Use OBS Studio, QuickTime, or Windows Game Bar (`Win + G`) at 1080p resolution.
2. **Audio:** Use a clean microphone with clear pacing matching the timestamps above.
3. **YouTube Title:** `PondPlan AI — Autonomous Farm Pond Siting & Catchment Analysis Demo`
4. **YouTube Playlist Link:** `https://www.youtube.com/playlist?list=PLMFQLz-BMw9M`
5. **YouTube Description:**
   ```
   Live Front-End (Primary): http://10.1.75.51:6241/
   Alternative Front-End: http://10.1.75.51:5241/ | http://10.1.75.51:3241/
   Swagger Docs: http://10.1.75.51:6241/docs
   GitHub Repository: https://github.com/Devendar9989/pond-planning
   YouTube Demo Link: https://www.youtube.com/playlist?list=PLMFQLz-BMw9M
   ```
