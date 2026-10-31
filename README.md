# Alcohol Absorption and Breath Alcohol Concentration Modeling - Python + Streamlit + Docker

🔗 Project website: [https://luisgoma4.github.io/Alcohol-web/](https://luisgoma4.github.io/Alcohol-web/)  

---

## 📖 Overview  

This repository presents an **academic-oriented implementation of alcohol absorption and exhalation dynamics** through **data fitting and theoretical modeling in Python**.  
The project is grounded in pharmacokinetic formulations describing **ethanol absorption, distribution, and elimination** after oral ingestion. The model focuses on the relationship between **ingested dose, absorption rate, elimination rate, and distribution volume** in order to predict **breath alcohol concentration (BrAC) over time**.  

The implementation has been designed to serve both **didactic** and **research-related purposes**, combining rigorous mathematical modeling with accessible visualization tools.  

---

## 🔬 Theoretical Model  

The computational approach relies on a simplified **Michaelis–Menten-type pharmacokinetic model** (e.g., Martin et al., 1984), which describes BrAC as:  

\[
C(t) = \frac{D \cdot k_a}{V_d (k_a - k_e)} \left(e^{-k_e t} - e^{-k_a t}\right)
\]

Where:  
- \(C(t)\): Breath alcohol concentration at time *t*  
- \(D\): Alcohol dose (mg/kg or equivalent)  
- \(k_a\): Absorption rate constant  
- \(k_e\): Elimination rate constant  
- \(V_d\): Volume of distribution  

This formula captures the **rise and fall of BrAC**:  
- The initial exponential rise corresponds to **alcohol absorption**.  
- The peak and subsequent decline are controlled by **distribution and elimination kinetics**.  

Experimental datasets can be used for **data fitting of \(k_a\), \(k_e\), and \(V_d\)** to improve predictive accuracy across individuals.  

---

## 📊 Data Fitting  

Python’s **SciPy** and **NumPy** libraries are employed for:  
- **Curve fitting** experimental data to the model equation.  
- Estimating **subject-specific parameters** (e.g., habitual tolerance, body composition).  
- Producing **statistical measures** of model accuracy (R², RMSE).  

The fitting process enables direct comparison between **simulated trajectories** and **empirical BrAC measurements**, ensuring both **theoretical rigor** and **practical validation**.  

---

## 💻 Implementation  

### Python  
The entire modeling workflow is written in **Python 3**, with emphasis on reproducibility and modularity:  
- **NumPy**: Numerical computations  
- **SciPy**: Optimization and curve fitting  
- **Matplotlib / Plotly**: Visualization  
- **Pandas**: Data handling  

### Streamlit  
A **Streamlit application** is provided to enable interactive exploration of the model:  
- Users can input **dose, body parameters, and time settings**.  
- Interactive plots show the **simulated BrAC curve** and related statistics.  
- Didactic tables provide context for **physiological constants and parameters**.  

This allows the model to be used **in-browser** as a teaching and research tool without requiring advanced programming knowledge.  

### Docker  
To ensure **portability and reproducibility**, a **Docker container** is included:  
- Provides an **isolated runtime environment** with all dependencies pre-installed.  
- Ensures consistent execution across operating systems (macOS, Linux, Windows).  
- Facilitates deployment on servers for **web-accessible simulations**.  

---

## 🚀 Usage  

### Local Execution  
```bash
git clone https://github.com/luisgoma4/Alcohol-web.git
cd Alcohol-web
pip install -r requirements.txt
streamlit run streamlit_app.py

```

### Using the web app

1. **About you** – sex, age, weight and height.
2. **What have you had?** – one tap per drink (small beer, bottle of beer, glass of wine, mixed drink, shot) adds it at the current time; edit time, drink or amount in the table.
3. **Have you eaten?** – empty stomach / light snack / full meal.
4. **Result** – peak breath and blood alcohol, and the time you'll be back under your limit (general or novice/professional).

Model parameters (absorption, elimination, BBR, tolerance, time step…) have standard values and are tucked away under **Advanced model options**, with a button to restore them.

The interface is available in Spanish and English. Everything the user enters is remembered **only in their browser** (`localStorage`); nothing is stored on the server. **Forget my data** erases it.
