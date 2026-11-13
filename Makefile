
build:
	nuitka --mode=onefile --output-dir=./bin --output-filename=tex2html tex2html.py

clean:
	rm -rf ./bin
